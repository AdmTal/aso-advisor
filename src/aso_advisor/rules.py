"""The audit rules.

Each rule reads the metadata of one version and returns `Suggestion` objects.
The rules encode the search mechanics of the App Store:

- The name (30 characters) has more ranking weight than the subtitle (30), and
  the subtitle has more weight than the keyword field (100).
- The store indexes each word one time per storefront. A word that you repeat
  in the title, the subtitle, the keyword field, or in a cross-indexed
  localization gives no extra rank. It only costs characters.
- The store makes a search phrase from the words of ONE localization. It does
  not combine words from two localizations.
- Singular and plural forms do not always match. Index the form that the user
  types.
- The description does not feed keyword rank. It feeds the discovery tags of
  Apple and the assistants that recommend apps.
- The promotional text (170 characters) is conversion copy. You can change it
  without a new release.

Read `docs/rules.md` for the reference of all rules and `docs/concepts.md` for
the mechanics behind them.
"""

from dataclasses import dataclass, field

from .model import BULLET_CHARS, IMPLICIT_TOKENS, LIMITS, Suggestion, tokens


@dataclass
class RuleContext:
    """Everything that a rule needs to look at one metadata version."""

    locales: dict
    strategy: object
    groups: dict
    primary_locale: str = 'en-US'
    default_country: str = 'us'
    version: str = '?'
    prev_locales: dict = field(default_factory=dict)
    prev_version: str = ''

    @property
    def primary_group(self):
        """The storefront group of the home market."""
        wanted = (self.default_country or '').upper()
        if wanted in self.groups:
            return wanted
        for gid, (_name, codes) in self.groups.items():
            if codes and codes[0] == self.primary_locale:
                return gid
        for gid, (_name, codes) in self.groups.items():
            if self.primary_locale in codes:
                return gid
        return next(iter(self.groups), '')

    def group_locales(self, group_id):
        """The localizations of a group that have metadata."""
        _name, codes = self.groups[group_id]
        return [self.locales[c] for c in codes if c in self.locales]

    def group_name(self, group_id):
        return self.groups[group_id][0]

    def groups_of(self, code):
        """Every group that indexes the localization `code`."""
        return [gid for gid, (_n, codes) in self.groups.items() if code in codes]


ALL_RULES = [
    'LIMIT', 'FORMAT', 'EMPTY', 'BUDGET', 'DUP_FIELD', 'DUP_TITLE',
    'TITLE_SUB_DUP', 'MULTIWORD', 'AI_TAGS', 'DESC_DEPTH', 'DEAD_TITLE',
    'DUP_XLOC', 'DUP_XLOC_STRUCT', 'TITLE_REDUNDANT', 'PLURAL', 'LOWVALUE',
    'TRADEMARK', 'TRADEMARK_SOFT', 'BRAND', 'PHRASE', 'SEED', 'STRATEGY',
    'PROMO', 'WHATSNEW', 'LOCALE', 'DIFF',
]

RULE_HELP = {
    'LIMIT': 'CRITICAL. A field is longer than App Store Connect accepts.',
    'FORMAT': 'LOW. The keyword field has spaces or empty entries.',
    'EMPTY': 'HIGH. The subtitle or the keyword field is empty.',
    'BUDGET': 'MEDIUM/LOW. A field does not use all of its characters.',
    'DUP_FIELD': 'HIGH. The same entry is twice in one keyword field.',
    'DUP_TITLE': 'HIGH. A keyword that the own title or subtitle already indexes.',
    'TITLE_SUB_DUP': 'HIGH. A word is in both the title and the subtitle.',
    'MULTIWORD': 'MEDIUM. A keyword entry has more than one word.',
    'AI_TAGS': 'LOW. The description opening misses your core category words.',
    'DESC_DEPTH': 'MEDIUM. A translated description drops whole sections.',
    'DEAD_TITLE': 'HIGH. A keyword that a cross-indexed title already gives free.',
    'DUP_XLOC': 'HIGH. The same word in two keyword fields of one storefront.',
    'DUP_XLOC_STRUCT': 'INFO. Cross-locale overlap that you cannot remove.',
    'TITLE_REDUNDANT': 'INFO. A title word that a cross-indexed keyword field also has.',
    'PLURAL': 'MEDIUM. The singular and the plural are both in one keyword field.',
    'LOWVALUE': 'MEDIUM. Words that the store ignores or does not allow.',
    'TRADEMARK': 'INFO. A trademark of another company, with review risk.',
    'TRADEMARK_SOFT': 'INFO. The name of a platform feature.',
    'BRAND': 'HIGH. A storefront cannot find you by your brand name.',
    'PHRASE': 'MEDIUM. No localization holds every word of a target phrase.',
    'SEED': 'MEDIUM. A high-value seed keyword that you index nowhere.',
    'STRATEGY': 'INFO. A trade-off from your strategy file.',
    'PROMO': 'MEDIUM/LOW. The promotional text is empty or short.',
    'WHATSNEW': 'LOW. The release notes are thin.',
    'LOCALE': 'LOW. A locale on your priority list has no metadata.',
    'DIFF': 'INFO. What changed since the version before.',
    'ASSET_MISSING': 'MEDIUM. A required locale has no screenshots.',
    'ASSET_ORPHAN': 'LOW. An assets directory has no metadata locale.',
    'ASSET_COUNT': 'CRITICAL. A set has more files than the store accepts.',
    'ASSET_SIZE': 'HIGH. A screenshot has an unexpected pixel size.',
    'ASSET_ALPHA': 'HIGH. A screenshot has an alpha channel.',
    'ASSET_VIDEO_LENGTH': 'HIGH. An app preview is not 15 to 30 seconds long.',
    'ASSET_DEVICE': 'LOW. The device directory is missing or not known.',
    'ASSET_ORDER': 'LOW. The file names do not show the display order.',
}


def run_all(ctx, disabled=()):
    """Run every rule and return the suggestions, most important first."""
    disabled = {r.upper() for r in disabled}
    out = []
    for fn in (
        check_limits,
        check_format,
        check_empty_fields,
        check_budget,
        check_duplicates_in_field,
        check_duplicates_vs_title,
        check_title_subtitle_overlap,
        check_multiword_entries,
        check_description_ai_alignment,
        check_description_depth,
        check_cross_locale_duplicates,
        check_keywords_vs_group_titles,
        check_title_redundant_vs_group_keywords,
        check_plural_pairs,
        check_low_value_terms,
        check_trademarks,
        check_brand_coverage,
        check_phrase_coverage,
        check_seed_opportunities,
        check_strategy_notes,
        check_conversion_fields,
        check_locale_coverage,
        check_changelog,
    ):
        out.extend(fn(ctx))
    out = [s for s in out if s.rule not in disabled]
    out.sort(key=lambda s: (s.severity_rank, s.scope, s.title))
    return out


# -- helpers ------------------------------------------------------------------

def _fmt_terms(terms, limit=8):
    terms = sorted(terms)
    shown = ', '.join(terms[:limit])
    if len(terms) > limit:
        shown += f', … (+{len(terms) - limit})'
    return shown


def _kw_token_carriers(ctx):
    """token -> the locale codes whose KEYWORD FIELD holds the token."""
    carriers = {}
    for meta in ctx.locales.values():
        if meta.is_non_spaced:
            continue
        for entry in meta.kw_entries:
            for tok in tokens(entry):
                carriers.setdefault(tok, set()).add(meta.code)
    return carriers


def _phrase_critical(ctx, meta, tok):
    """True when `tok` is the only reason this localization completes a target
    phrase. Phrases combine inside one localization, so a token can be a
    duplicate at token level and still be necessary here."""
    indexed = meta.indexed_tokens
    for phrase, _score, _why in ctx.strategy.phrase_targets:
        words = {w for w in tokens(phrase) if w not in ctx.strategy.phrase_stopwords}
        if tok in words and words <= indexed:
            return True
    return False


# -- hard limits --------------------------------------------------------------

def check_limits(ctx):
    """App Store Connect rejects a field that is too long."""
    out = []
    for meta in ctx.locales.values():
        for fld in ('name', 'subtitle', 'keywords', 'promotional_text',
                    'description', 'whats_new'):
            value = getattr(meta, fld)
            if value and len(value) > LIMITS[fld]:
                out.append(Suggestion(
                    'LIMIT', f'{meta.code}:{fld}', meta.code, 'CRITICAL',
                    f'{meta.code}: {fld} is {len(value)}/{LIMITS[fld]} characters — '
                    'App Store Connect rejects it',
                    detail='The upload fails until the field is short enough.',
                    fix=f'Cut {fld} to {LIMITS[fld]} characters.',
                ))
    return out


# -- wasted characters --------------------------------------------------------

def check_format(ctx):
    """Spaces and empty entries in the keyword field cost characters."""
    out = []
    for meta in ctx.locales.values():
        kw = meta.keywords
        if not kw:
            continue
        if ', ' in kw or ' ,' in kw:
            out.append(Suggestion(
                'FORMAT', f'{meta.code}:spaces', meta.code, 'LOW',
                f'{meta.code}: the keyword field has spaces next to commas',
                detail='Each space uses one of the 100 characters and adds nothing.',
                fix='Remove all spaces next to commas.',
            ))
        if ',,' in kw or kw.strip().endswith(','):
            out.append(Suggestion(
                'FORMAT', f'{meta.code}:empty', meta.code, 'LOW',
                f'{meta.code}: the keyword field has an empty entry or a comma at the end',
                fix='Remove the extra comma.',
            ))
    return out


def check_empty_fields(ctx):
    """An empty field is indexing surface that you do not use."""
    out = []
    for meta in ctx.locales.values():
        if not (meta.name or meta.subtitle or meta.keywords):
            continue  # The locale has descriptions only. Other rules cover it.
        if not meta.keywords.strip():
            out.append(Suggestion(
                'EMPTY', f'{meta.code}:keywords', meta.code, 'HIGH',
                f'{meta.code}: the keyword field is empty',
                detail='The keyword field gives 100 characters of indexing that costs '
                       'nothing and that no user sees.',
                fix='Add comma-separated single words. Do not repeat words from the '
                    'name or the subtitle.',
            ))
        if not meta.subtitle.strip():
            out.append(Suggestion(
                'EMPTY', f'{meta.code}:subtitle', meta.code, 'HIGH',
                f'{meta.code}: the subtitle is empty',
                detail='The subtitle is the second strongest ranking field. It also '
                       'appears under the app name on the product page.',
                fix='Write a subtitle of up to 30 characters. Use search words that '
                    'the name does not have.',
            ))
    return out


def check_budget(ctx):
    """Unused characters in a field are unused ranking surface."""
    out = []
    for meta in ctx.locales.values():
        free_kw = LIMITS['keywords'] - len(meta.keywords)
        if meta.keywords and free_kw >= 4:
            out.append(Suggestion(
                'BUDGET', f'{meta.code}:keywords', meta.code, 'MEDIUM',
                f'{meta.code}: {free_kw} unused keyword characters ({len(meta.keywords)}/100)',
                detail='Unused keyword characters are free ranking surface.',
                fix='Add one more term. See the seed-keyword suggestions in this report.',
            ))
        for fld in ('name', 'subtitle'):
            value = getattr(meta, fld)
            free = LIMITS[fld] - len(value)
            if value and free >= 6:
                out.append(Suggestion(
                    'BUDGET', f'{meta.code}:{fld}', meta.code, 'LOW',
                    f'{meta.code}: the {fld} uses only {len(value)}/{LIMITS[fld]} characters',
                    detail=f'The {fld} is the '
                           f'{"strongest" if fld == "name" else "second strongest"} ranking '
                           'field. Unused characters there are the most valuable space that '
                           'you have. Locales with dense scripts correctly need fewer '
                           'characters — judge by meaning.',
                    fix=f'Add one more search word to the {fld} if the text still reads well.',
                ))
    return out


# -- duplicates ---------------------------------------------------------------

def check_duplicates_in_field(ctx):
    """The same entry two times in one keyword field."""
    out = []
    for meta in ctx.locales.values():
        seen, dups = set(), set()
        for entry in meta.kw_entries:
            low = entry.lower()
            if low in seen:
                dups.add(entry)
            seen.add(low)
        if dups:
            out.append(Suggestion(
                'DUP_FIELD', f'{meta.code}:{_fmt_terms(dups)}', meta.code, 'HIGH',
                f'{meta.code}: duplicate keyword entries: {_fmt_terms(dups)}',
                detail='The store indexes a word one time. The second copy is waste.',
                fix='Delete the duplicates and use the characters for new terms.',
            ))
    return out


def check_duplicates_vs_title(ctx):
    """A keyword that the name or the subtitle of the same locale already has."""
    out = []
    for meta in ctx.locales.values():
        title_tokens = set(tokens(meta.name)) | set(tokens(meta.subtitle))
        wasted = set()
        if meta.is_non_spaced:
            # These titles mix scripts. Compare in lower case, because a Latin
            # token such as "hd" in the keyword field and "HD" in the title is
            # the same wasted slot.
            blob = ((meta.name or '') + (meta.subtitle or '')).lower()
            for entry in meta.kw_entries:
                if entry and entry.lower() in blob:
                    wasted.add(entry)
        else:
            for entry in meta.kw_entries:
                entry_tokens = set(tokens(entry))
                if entry_tokens and entry_tokens <= title_tokens:
                    wasted.add(entry)
        if wasted:
            chars = sum(len(w) + 1 for w in wasted)
            out.append(Suggestion(
                'DUP_TITLE', f'{meta.code}:{_fmt_terms(wasted)}', meta.code, 'HIGH',
                f'{meta.code}: keywords that the title or the subtitle already indexes: '
                f'{_fmt_terms(wasted)}',
                detail=f'The store indexes the words of the name and the subtitle with more '
                       f'weight. These entries waste about {chars} characters.',
                fix='Remove them from the keyword field and add new terms.',
            ))
    return out


def check_title_subtitle_overlap(ctx):
    """A word in both the name and the subtitle of one locale."""
    out = []
    for meta in ctx.locales.values():
        if meta.is_non_spaced or not meta.subtitle:
            continue
        overlap = (set(tokens(meta.name)) & set(tokens(meta.subtitle))) - IMPLICIT_TOKENS
        overlap = {w for w in overlap if len(w) > 2}
        if overlap:
            out.append(Suggestion(
                'TITLE_SUB_DUP', f'{meta.code}:{_fmt_terms(overlap)}', meta.code, 'HIGH',
                f'{meta.code}: word(s) in both the title and the subtitle: {_fmt_terms(overlap)}',
                detail='The title and the subtitle are the two strongest fields. The store '
                       'indexes a repeated word one time, so the second use wastes premium '
                       'characters.',
                fix='Write the subtitle again with new search words.',
            ))
    return out


def check_multiword_entries(ctx):
    """Spaces inside a keyword entry buy nothing."""
    out = []
    for meta in ctx.locales.values():
        if meta.is_non_spaced:
            continue
        spaced = [e for e in meta.kw_entries if ' ' in e]
        if spaced:
            wasted = sum(e.count(' ') for e in spaced)
            out.append(Suggestion(
                'MULTIWORD', f'{meta.code}:{_fmt_terms(spaced)}', meta.code, 'MEDIUM',
                f'{meta.code}: keyword entries with more than one word: {_fmt_terms(spaced)}',
                detail=f'The store makes the phrases from the single words. The {wasted} '
                       'space(s) buy nothing.',
                fix='Split the entries into single words. Then delete the words that are '
                    'now duplicates.',
            ))
    return out


# -- descriptions -------------------------------------------------------------

def check_description_ai_alignment(ctx):
    """Apple makes the discovery tags from the description."""
    terms = ctx.strategy.ai_tag_terms
    if not terms:
        return []
    language = ctx.primary_locale.split('-')[0]
    out = []
    for meta in ctx.locales.values():
        if not meta.description or not meta.code.startswith(language):
            continue
        head = ' '.join(tokens(meta.description[:500]))
        missing = [t for t in terms if t not in head]
        if len(missing) > len(terms) // 2:
            out.append(Suggestion(
                'AI_TAGS', f'{meta.code}:{_fmt_terms(missing)}', meta.code, 'LOW',
                f'{meta.code}: the start of the description does not have these core '
                f'category words: {_fmt_terms(missing)}',
                detail='Apple makes the discovery tags from the description. Assistants '
                       'that recommend apps also read it. The first paragraphs must say '
                       'plainly what the app does.',
                fix='Put the missing words into the first two paragraphs in a natural way.',
            ))
    return out


def _desc_shape(text):
    """(number of paragraphs, number of bullets) of a description."""
    paragraphs = [p for p in (text or '').split('\n\n') if p.strip()]
    bullets = [line for line in (text or '').split('\n')
               if line.strip() and line.strip()[0] in BULLET_CHARS]
    return len(paragraphs), len(bullets)


def check_description_depth(ctx):
    """A localization that drops whole sections of the primary description.

    The test looks at structure, not at length. A character count punishes the
    languages that are more compact, and it does not find a locale that is long
    but incomplete.
    """
    source = ctx.locales.get(ctx.primary_locale)
    if source is None or not source.description:
        return []
    want_paragraphs, want_bullets = _desc_shape(source.description)
    if want_paragraphs < 3:
        return []
    out = []
    for meta in sorted(ctx.locales.values(), key=lambda m: m.code):
        if not meta.description or meta.code == source.code:
            continue
        paragraphs, bullets = _desc_shape(meta.description)
        gaps = []
        if paragraphs < want_paragraphs:
            gaps.append(f'{want_paragraphs - paragraphs} of {want_paragraphs} paragraphs')
        if bullets < want_bullets:
            gaps.append(f'{want_bullets - bullets} of {want_bullets} feature bullets')
        if not gaps:
            continue
        out.append(Suggestion(
            'DESC_DEPTH', meta.code, meta.code, 'MEDIUM',
            f'{meta.code}: the description does not have {" and ".join(gaps)}',
            detail=f'This locale has a short rewrite, not a full translation. That market '
                   f'never sees the sections that the text drops. The description uses '
                   f'{len(meta.description)} of {LIMITS["description"]} characters.',
            fix=f'Translate the missing sections from {source.code}. Add them to the '
                'existing text, so that the terms already in use stay the same.',
        ))
    return out


# -- cross-localization -------------------------------------------------------

def check_keywords_vs_group_titles(ctx):
    """A keyword field that pays for a word that a cross-indexed title gives free.

    `check_duplicates_vs_title` compares a locale against its own title.
    `check_cross_locale_duplicates` compares keyword field against keyword
    field. This class of waste falls between the two. Two conditions keep the
    rule honest. A token is waste only if it is redundant in EVERY storefront
    where the locale appears. A token is never waste if it holds up a target
    phrase inside its own localization.
    """
    out = []
    for code, meta in sorted(ctx.locales.items()):
        gids = ctx.groups_of(code)
        if not gids:
            continue
        redundant_everywhere, suppliers = None, {}
        for gid in gids:
            _name, codes = ctx.groups[gid]
            free = set()
            for other in codes:
                if other == code or other not in ctx.locales:
                    continue
                other_meta = ctx.locales[other]
                supplied = set(tokens(other_meta.name)) | set(tokens(other_meta.subtitle))
                for tok in supplied:
                    free.add(tok)
                    suppliers.setdefault(tok, set()).add(other)
            here = {t for e in meta.kw_entries for t in tokens(e) if t in free}
            redundant_everywhere = here if redundant_everywhere is None \
                else (redundant_everywhere & here)
            if not redundant_everywhere:
                break
        wasted = {t for t in (redundant_everywhere or set())
                  if not _phrase_critical(ctx, meta, t)}
        if not wasted:
            continue
        chars = sum(len(t) + 1 for t in wasted)
        detail_bits = ', '.join(f'{t} (from {"/".join(sorted(suppliers[t]))})'
                                for t in sorted(wasted))
        out.append(Suggestion(
            'DEAD_TITLE', f'{code}:{_fmt_terms(wasted)}', code, 'HIGH',
            f'{code}: keywords that a cross-indexed title already gives: {_fmt_terms(wasted)}',
            detail=f'{detail_bits}. The store indexes titles and subtitles for the whole '
                   f'storefront, so these keyword characters buy nothing. About {chars} '
                   'characters are recoverable.',
            fix='Remove them from the keyword field. Spend the characters on terms that no '
                'other localization of the storefront has.',
        ))
    return out


def check_cross_locale_duplicates(ctx):
    """The same word in two keyword fields that index in the same storefront.

    A locale can correctly hold a token that a group partner also holds, if it
    is the only carrier of that token in a different storefront group. Those
    carriers are justified. The fix text names the locale that must drop the
    term.
    """
    out = []
    all_carriers = _kw_token_carriers(ctx)

    def justified(code, tok, current_gid):
        for gid, (_name, codes) in ctx.groups.items():
            if gid == current_gid or code not in codes:
                continue
            if all_carriers.get(tok, set()) & set(codes) == {code}:
                return True
        return False

    for gid, (label, codes) in ctx.groups.items():
        present = ctx.group_locales(gid)
        if len(present) < 2:
            continue
        dups = {}
        for tok, carriers in all_carriers.items():
            in_group = carriers & {m.code for m in present}
            if len(in_group) > 1:
                dups[tok] = in_group
        if not dups:
            continue
        advice, structural = [], []
        for tok, carrier_set in sorted(dups.items()):
            keep = {c for c in carrier_set if justified(c, tok, gid)}
            drop = carrier_set - keep
            if drop and keep:
                advice.append(f'{tok}: remove from {"/".join(sorted(drop))} '
                              f'(keep in {"/".join(sorted(keep))} — needed elsewhere)')
            elif drop:
                advice.append(f'{tok}: keep one of {"/".join(sorted(drop))}, remove the rest')
            else:
                structural.append(tok)
        pretty = ', '.join(f'{t} ({"+".join(sorted(c))})' for t, c in sorted(dups.items())[:8])
        if len(dups) > 8:
            pretty += f', … (+{len(dups) - 8})'
        if advice:
            out.append(Suggestion(
                'DUP_XLOC', f'{gid}:{_fmt_terms(dups)}', gid, 'HIGH',
                f'{label} storefront: the same keyword is in more than one cross-indexed '
                f'locale: {pretty}',
                detail=f'The {label} storefront indexes these localizations together '
                       f'({", ".join(c for c in codes if c in ctx.locales)}). A word counts '
                       'one time, so each repeat is a wasted slot.',
                fix='; '.join(advice[:6]),
            ))
        if structural:
            out.append(Suggestion(
                'DUP_XLOC_STRUCT', f'{gid}:{_fmt_terms(structural)}', gid, 'INFO',
                f'{label} storefront: keyword overlap that you cannot remove: '
                f'{_fmt_terms(structural)}',
                detail='Each carrier of these tokens is the only carrier in a different '
                       'storefront group. The overlap here is structural, not waste.',
            ))
    return out


def check_title_redundant_vs_group_keywords(ctx):
    """The mirror of DEAD_TITLE: a title word that a cross-indexed keyword field
    already carries.

    The severity is INFO, and the difference is important. The presence is
    redundant, but the weight is not. The subtitle is the second ranking field
    and a keyword field is the third. If you delete the word from the title,
    the app stays indexed for it, but with less weight. The question is whether
    those premium characters have a better use.
    """
    out = []
    kw_carriers = _kw_token_carriers(ctx)

    def sole_carrier_elsewhere(code, tok, this_gid):
        for gid, (_name, codes) in ctx.groups.items():
            if gid == this_gid or code not in codes:
                continue
            if kw_carriers.get(tok, set()) & set(codes) == {code}:
                return True
        return False

    for gid, (label, codes) in ctx.groups.items():
        present = [c for c in codes if c in ctx.locales]
        if len(present) < 2:
            continue
        for code in present:
            meta = ctx.locales[code]
            if meta.is_non_spaced:
                continue
            titled = set(tokens(meta.name)) | set(tokens(meta.subtitle))
            for tok in sorted(titled - IMPLICIT_TOKENS):
                if len(tok) <= 2:
                    continue
                holders = [o for o in present if o != code and o in kw_carriers.get(tok, set())]
                keepers = [o for o in holders if sole_carrier_elsewhere(o, tok, gid)]
                if not keepers:
                    continue
                out.append(Suggestion(
                    'TITLE_REDUNDANT', f'{gid}:{code}:{tok}', code, 'INFO',
                    f'{code}: "{tok}" in the title or the subtitle is also in the keyword '
                    f'field of {"/".join(keepers)} for the {label} storefront',
                    detail=f'{"/".join(keepers)} cannot remove it, because that locale is '
                           f'the only carrier of "{tok}" in a different storefront. The '
                           f'{code} use is redundant for presence but not for weight. The '
                           'title and the subtitle rank higher than a keyword field, so a '
                           f'removal moves "{tok}" to keyword weight in {label}.',
                    fix=f'Change this only if a better term needs the space. Write the '
                        f'{code} subtitle again without "{tok}" and let '
                        f'{"/".join(keepers)} carry it.',
                ))
    return out


def check_plural_pairs(ctx):
    """The singular form and the plural form in the same keyword field."""
    out = []
    for meta in ctx.locales.values():
        if meta.is_non_spaced:
            continue
        kw_tokens = set()
        for entry in meta.kw_entries:
            kw_tokens.update(tokens(entry))
        kw_tokens -= IMPLICIT_TOKENS
        pairs = sorted(
            f'{t}/{t}s' for t in kw_tokens
            if len(t) > 2 and (t + 's' in kw_tokens or t + 'es' in kw_tokens)
        )
        if pairs:
            out.append(Suggestion(
                'PLURAL', f'{meta.code}:{",".join(pairs)}', meta.code, 'MEDIUM',
                f'{meta.code}: the keyword field has both forms: {", ".join(pairs)}',
                detail='The store usually matches one form to the other. Both forms cost a '
                       'slot. Keep the form that users type.',
                fix='Remove one form, usually the plural, and add a new term.',
            ))
    return out


# -- term quality -------------------------------------------------------------

def check_low_value_terms(ctx):
    """Words that the store ignores, indexes free, or does not allow."""
    out = []
    for meta in ctx.locales.values():
        bad = {e for e in meta.kw_entries if e.lower() in ctx.strategy.low_value_terms}
        if bad:
            out.append(Suggestion(
                'LOWVALUE', f'{meta.code}:{_fmt_terms(bad)}', meta.code, 'MEDIUM',
                f'{meta.code}: low-value keywords: {_fmt_terms(bad)}',
                detail='Words such as "app", "free", and "best" are ignored or indexed free. '
                       'Device names and platform names break the metadata rules of Apple.',
                fix='Replace them with terms that users type in search.',
            ))
    return out


def check_trademarks(ctx):
    """Trademarks of other companies: traffic against review risk."""
    out = []
    hard, soft = {}, {}
    for meta in ctx.locales.values():
        for entry in meta.kw_entries:
            low = entry.lower()
            if low in ctx.strategy.trademark_terms:
                hard.setdefault(low, []).append(meta.code)
            elif low in ctx.strategy.soft_trademark_terms:
                soft.setdefault(low, []).append(meta.code)
    if hard:
        pretty = ', '.join(f'{t} ({"+".join(sorted(set(c)))})' for t, c in sorted(hard.items()))
        out.append(Suggestion(
            'TRADEMARK', _fmt_terms(hard), 'global', 'INFO',
            f'Trademarks of other companies in keyword fields: {pretty}',
            detail='These terms often convert well, but they are a rejection risk under '
                   'App Review guideline 2.3.7. To keep them is a valid bet. Make the bet '
                   'on purpose. If a metadata rejection names this rule, remove these terms '
                   'first.',
        ))
    if soft:
        pretty = ', '.join(f'{t} ({"+".join(sorted(set(c)))})' for t, c in sorted(soft.items()))
        out.append(Suggestion(
            'TRADEMARK_SOFT', _fmt_terms(soft), 'global', 'INFO',
            f'Platform feature names in keyword fields: {pretty}',
            detail='Feature names carry a lower risk than brand names, and they bring '
                   'traffic with clear intent.',
        ))
    return out


# -- brand --------------------------------------------------------------------

def check_brand_coverage(ctx):
    """Users who know your name must find you."""
    phrases = ctx.strategy.brand_phrases
    if not phrases:
        return []
    uncovered = []
    for gid, (label, _codes) in ctx.groups.items():
        present = ctx.group_locales(gid)
        if not present:
            continue
        covered = any(set(tokens(phrase)) <= meta.indexed_tokens
                      for phrase in phrases for meta in present)
        if not covered:
            uncovered.append(label)
    if not uncovered:
        return []
    shown = ', '.join(uncovered[:12])
    if len(uncovered) > 12:
        shown += f', … (+{len(uncovered) - 12})'
    primary = phrases[0]
    return [Suggestion(
        'BRAND', primary, 'global', 'HIGH',
        f'Branded search "{primary}" is not covered in: {shown}',
        detail='A store title that starts with keywords does not always contain the brand '
               'name. A user who heard your name finds you only when every word of the '
               'brand is indexed in one localization of that storefront. Branded traffic '
               'converts better than any other traffic.',
        fix=f'Put the words of "{primary}" together in one localization per storefront. '
            f'The {ctx.primary_locale} keyword field is usually the cheapest place.',
    )]


# -- long-tail phrases --------------------------------------------------------

def phrase_coverage_matrix(ctx):
    """{group: [(phrase, score, covering_locale, missing_words, nearest_locale)]}"""
    matrix = {}
    for gid in ctx.groups:
        present = ctx.group_locales(gid)
        if not present:
            continue
        rows = []
        for phrase, score, _why in ctx.strategy.phrase_targets:
            want = [w for w in tokens(phrase) if w not in ctx.strategy.phrase_stopwords]
            best, best_missing = None, None
            for meta in present:
                missing = [w for w in want if w not in meta.indexed_tokens]
                if not missing:
                    best, best_missing = meta.code, []
                    break
                if best_missing is None or len(missing) < len(best_missing):
                    best, best_missing = meta.code, missing
            rows.append((phrase, score, best if not best_missing else None,
                         best_missing or [], best))
        matrix[gid] = rows
    return matrix


def check_phrase_coverage(ctx):
    """Only the home storefront makes suggestions. The report has the matrix of
    every storefront."""
    out = []
    gid = ctx.primary_group
    matrix = phrase_coverage_matrix(ctx)
    for phrase, score, covered_by, missing, nearest in matrix.get(gid, []):
        if covered_by or score < 5:
            continue
        out.append(Suggestion(
            'PHRASE', f'{gid}:{phrase}', gid, 'MEDIUM',
            f'{ctx.group_name(gid)} storefront: incomplete keyword coverage for "{phrase}" '
            f'(score {score}/10)',
            detail=f'The nearest localization is {nearest}. It does not have: '
                   f'{", ".join(missing)}. Semantic matching can still rank the app for '
                   'this query, but full coverage of all words in ONE localization gives a '
                   'better position.',
            fix=f'Add {", ".join(missing)} to {nearest}, in the name, the subtitle, or the '
                'keyword field.',
        ))
    return out


# -- seeds and strategy notes -------------------------------------------------

def uncovered_seeds(ctx, group_id=None):
    """Seed keywords that no localization of the group indexes."""
    gid = group_id or ctx.primary_group
    if gid not in ctx.groups:
        return []
    indexed = set()
    for meta in ctx.group_locales(gid):
        indexed |= meta.indexed_tokens
    return [(t, s, why) for t, s, why in ctx.strategy.seed_keywords if t.lower() not in indexed]


def check_seed_opportunities(ctx):
    """High-value seed keywords that you do not index yet."""
    gid = ctx.primary_group
    out = []
    for term, score, why in uncovered_seeds(ctx, gid):
        if score < 5:
            continue
        out.append(Suggestion(
            'SEED', f'{gid}:{term}', gid, 'MEDIUM',
            f'{ctx.group_name(gid)} storefront: high-value keyword indexed nowhere: '
            f'"{term}" (score {score}/10)',
            detail=why or 'This term is in your strategy file but no localization of the '
                          'storefront indexes it.',
            fix='Add it to the localization of the group that has free characters, or '
                'exchange it for the weakest term. See the proposed keyword lines in the '
                'report.',
        ))
    return out


def check_strategy_notes(ctx):
    """Your own trade-offs, shown in every run so that they stay conscious."""
    return [Suggestion('STRATEGY', key, 'global', 'INFO', title, detail=detail)
            for key, title, detail in ctx.strategy.notes]


# -- conversion ---------------------------------------------------------------

def check_conversion_fields(ctx):
    """The promotional text and the release notes change conversion, not rank."""
    out = []
    for meta in ctx.locales.values():
        if not (meta.description or meta.promotional_text or meta.whats_new):
            continue
        if not meta.promotional_text.strip():
            out.append(Suggestion(
                'PROMO', f'{meta.code}:missing', meta.code, 'MEDIUM',
                f'{meta.code}: the promotional text is empty',
                detail='The promotional text gives 170 characters at the top of the product '
                       'page. You can change it WITHOUT a new release. It is the best place '
                       'for a limited-time message or for a conversion test.',
                fix='Write one sentence that says what the user gets. Test a new one each '
                    'month.',
            ))
        elif len(meta.promotional_text) < 80:
            out.append(Suggestion(
                'PROMO', f'{meta.code}:short', meta.code, 'LOW',
                f'{meta.code}: the promotional text uses only '
                f'{len(meta.promotional_text)}/170 characters',
                fix='Use all 170 characters. This text is pure conversion copy.',
            ))
        if meta.whats_new and len(meta.whats_new.strip()) < 40:
            out.append(Suggestion(
                'WHATSNEW', meta.code, meta.code, 'LOW',
                f'{meta.code}: the release notes are thin '
                f'({len(meta.whats_new.strip())} characters)',
                detail='Returning visitors read the release notes. They show that you '
                       'maintain the app. Generic notes lower conversion.',
                fix='Name one concrete improvement for the user in each release.',
            ))
    return out


# -- locale coverage ----------------------------------------------------------

def check_locale_coverage(ctx):
    """Locales with no metadata are storefronts with no indexing."""
    from .storefronts import ASC_LOCALES

    missing = [c for c in ASC_LOCALES if c not in ctx.locales]
    if not missing:
        return []
    prioritized = [c for c in ctx.strategy.locale_priority if c in missing]
    if not prioritized:
        return []
    lines = '; '.join(f'{c} — {ctx.strategy.locale_priority[c]}' for c in prioritized[:5])
    return [Suggestion(
        'LOCALE', _fmt_terms(prioritized), 'global', 'LOW',
        f'{len(missing)} App Store locales have no metadata (first choices: '
        f'{", ".join(prioritized[:5])})',
        detail='Each localization adds 100 keyword characters and 60 title and subtitle '
               f'characters of indexing in its storefronts. Priorities: {lines}',
        fix='Copy the nearest localization that exists and translate it.',
    )]


# -- version differences ------------------------------------------------------

def check_changelog(ctx):
    """A record of what changed since the version before."""
    if not ctx.prev_locales:
        return []
    changes = []
    for code in sorted(set(ctx.locales) | set(ctx.prev_locales)):
        current, old = ctx.locales.get(code), ctx.prev_locales.get(code)
        if current is None:
            changes.append(f'{code}: locale removed')
            continue
        if old is None:
            changes.append(f'{code}: locale added')
            continue
        for fld in ('name', 'subtitle'):
            if getattr(current, fld) != getattr(old, fld):
                changes.append(f'{code}: {fld} "{getattr(old, fld)}" → "{getattr(current, fld)}"')
        current_kw = {e.lower() for e in current.kw_entries}
        old_kw = {e.lower() for e in old.kw_entries}
        added, removed = current_kw - old_kw, old_kw - current_kw
        if added or removed:
            bits = []
            if added:
                bits.append(f'+{_fmt_terms(added)}')
            if removed:
                bits.append(f'-{_fmt_terms(removed)}')
            changes.append(f'{code}: keywords {" / ".join(bits)}')
    if not changes:
        return []
    shown = changes[:12]
    more = f' (+{len(changes) - 12} more)' if len(changes) > 12 else ''
    return [Suggestion(
        'DIFF', f'{ctx.prev_version}->{ctx.version}', 'global', 'INFO',
        f'Metadata changes {ctx.prev_version} → {ctx.version}: {len(changes)} field(s)',
        detail='\n'.join(shown) + more,
    )]


# -- proposed keyword lines (report appendix, not stored) ---------------------

def propose_keyword_lines(ctx, group_id=None):
    """Deterministic rewrite proposals for the keyword fields of a group.

    The algorithm is greedy. First it fills the free characters with the best
    seed keywords that you do not index. Then it exchanges the weakest terms
    for stronger seeds. Read the result before you use it.
    """
    gid = group_id or ctx.primary_group
    if gid not in ctx.groups:
        return []
    present = ctx.group_locales(gid)
    candidates = [(t, s) for t, s, _why in uncovered_seeds(ctx, gid) if s >= 4 and t.isascii()]
    candidates.sort(key=lambda item: -item[1])
    queue = [t for t, _s in candidates]
    phrase_words = ctx.strategy.phrase_words

    def value(term):
        low = term.lower()
        if low in ctx.strategy.low_value_terms:
            return 0.2
        if low in ctx.strategy.trademark_terms:
            return 5.0  # A deliberate bet. Do not propose to remove it.
        score = ctx.strategy.seed_score(low)
        if score is not None:
            return float(score)
        # Never remove the only carrier of a word that a target phrase needs.
        return 6.0 if low in phrase_words else 3.0

    proposals = []
    for meta in present:
        if meta.is_non_spaced or not meta.keywords:
            continue
        entries = list(meta.kw_entries)
        changed = []
        while queue:
            nxt = queue[0]
            if len(','.join(entries)) + 1 + len(nxt) <= LIMITS['keywords']:
                entries.append(queue.pop(0))
                changed.append(f'+{nxt}')
            else:
                break
        for _ in range(4):
            if not queue:
                break
            weakest = min(entries, key=value)
            nxt = queue[0]
            if value(nxt) <= value(weakest):
                break
            trial = [e for e in entries if e != weakest] + [nxt]
            if len(','.join(trial)) <= LIMITS['keywords']:
                entries = trial
                changed.append(f'-{weakest}+{nxt}')
                queue.pop(0)
        if changed:
            proposals.append((meta.code, meta.keywords, ','.join(entries), changed))
    return proposals
