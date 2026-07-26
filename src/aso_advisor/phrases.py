"""`aso phrases`: propose the target search phrases.

Every other part of the tool takes `phrase_targets` as given. This module makes
them. It asks the store what people type, then it scores each candidate against
what you already index.

Four sources feed the list:

- **The autocomplete of the App Store.** Apple sorts the completions by
  popularity, so the position is the closest free signal to search volume.
  A completion is a real query: somebody typed it.
- **The titles and subtitles of your competitors.** A strong app in your
  category does not choose those words by accident.
- **The words of your recent reviews**, with `--with-reviews`. Users search
  with the words that they write.
- **Your own seed keywords**, which set the direction of the search.

Nothing here is automatic truth. The command prints a ranked list with the
reason for each score. You choose, then `--write` puts your choice into
`strategy.yaml`.
"""

import re
import time
from pathlib import Path

import yaml

from . import store_api
from .model import tokens

MIN_WORDS = 2
MAX_WORDS = 5
MAX_ROOTS = 40

GENERIC_WORDS = {'app', 'apps', 'free', 'best', 'top', 'new', 'pro', 'lite',
                 'download', 'the', 'and', 'for', 'with'}


def _score_from_position(position):
    """Position 1 is the most searched completion. Position 12 is faint."""
    if position <= 1:
        return 10.0
    if position >= 12:
        return 2.0
    return round(10.0 - (position - 1) * 0.75, 2)


def _clean(term):
    text = re.sub(r'\s+', ' ', str(term or '')).strip().lower()
    return text.strip('-–—:,.')


# The autocomplete also returns the names of apps. A name is not a query, and
# it makes a bad target phrase. Two marks give it away: a separator that a
# brand uses, and a word that appears two times.
NAME_MARKS = (':', '|', '，', '، ', ' - ', '–', '—')


def _looks_like_an_app_name(raw, words):
    if any(mark in raw for mark in NAME_MARKS):
        return True
    return len(words) != len(set(words))


def collect_roots(ws, extra=()):
    """The terms to expand through the autocomplete."""
    strategy = ws.strategy
    roots = []
    for item in list(extra) + list(strategy.discovery_seeds):
        if _clean(item):
            roots.append(_clean(item))
    # The strongest seed keywords are also good roots. A one-word root returns
    # the whole family of queries that starts with it.
    for term, score, _why in sorted(strategy.seed_keywords, key=lambda s: -s[1]):
        if score >= 6 and _clean(term):
            roots.append(_clean(term))
    for phrase, _score, _why in strategy.phrase_targets:
        if _clean(phrase):
            roots.append(_clean(phrase))
    seen, out = set(), []
    for root in roots:
        if root not in seen:
            seen.add(root)
            out.append(root)
    return out[:MAX_ROOTS]


def competitor_phrases(ws, conn, country, ttl_hours):
    """Word groups from the titles and subtitles of the tracked competitors."""
    ids = list(ws.strategy.competitors)
    if not ids:
        return {}
    try:
        results = store_api.lookup(conn, track_ids=ids, country=country,
                                   ttl_hours=ttl_hours)
    except store_api.StoreAPIError:
        return {}
    found = {}
    for app in results:
        name = app.get('trackName') or ''
        # The part before the first separator is usually the brand name.
        parts = re.split(r'[:\-–—|,&]', name)
        pieces = parts[1:] if len(parts) > 1 else parts
        for piece in pieces:
            words = [w for w in tokens(piece) if w not in GENERIC_WORDS]
            for size in (2, 3):
                for index in range(len(words) - size + 1):
                    phrase = ' '.join(words[index:index + size])
                    found.setdefault(phrase, set()).add(
                        (app.get('trackName') or '?')[:28])
    return found


def review_words(ws, conn, countries, ttl_hours, pages=2):
    """{word: count} from the recent reviews."""
    from .live import REVIEW_STOPWORDS

    track_id = ws.config.app.track_id
    if not track_id:
        return {}
    counts = {}
    for country in countries:
        for review in store_api.reviews(conn, track_id, country=country, pages=pages,
                                        ttl_hours=ttl_hours):
            for word in set(tokens(f'{review["title"]} {review["body"]}')):
                if len(word) > 2 and word not in REVIEW_STOPWORDS:
                    counts[word] = counts.get(word, 0) + 1
    return counts


def coverage(phrase, group_locales, stopwords):
    """(covering locale or None, missing words, nearest locale)."""
    want = [w for w in tokens(phrase) if w not in stopwords]
    best, best_missing = None, None
    for meta in group_locales:
        missing = [w for w in want if w not in meta.indexed_tokens]
        if not missing:
            return meta.code, [], meta.code
        if best_missing is None or len(missing) < len(best_missing):
            best, best_missing = meta.code, missing
    return None, best_missing or want, best


def generate(ws, conn, country=None, deep=False, fresh=False, with_reviews=False,
             limit=25, extra_roots=()):
    """Return (phrase candidates, seed candidates)."""
    from .live import group_indexed_tokens, latest_locales

    country = (country or ws.config.app.default_country).lower()
    ttl = 0 if fresh else ws.config.cache_hours
    strategy = ws.strategy
    locales = latest_locales(ws)
    indexed, group_id = group_indexed_tokens(ws, locales, country)
    groups = ws.config.groups()
    group_locales = [locales[c] for c in groups.get(group_id, ('', []))[1]
                     if c in locales] if group_id in groups else list(locales.values())
    have = {_clean(p) for p, _s, _w in strategy.phrase_targets}

    roots = collect_roots(ws, extra_roots)
    if not roots:
        return [], []
    print(f'Reading the autocomplete of {country.upper()} for {len(roots)} root '
          f'term(s)…')

    hits = {}          # phrase -> {'position': int, 'roots': set}
    seen_roots = set()
    queue = list(roots)
    while queue:
        root = queue.pop(0)
        if root in seen_roots:
            continue
        seen_roots.add(root)
        try:
            suggestions = store_api.hints(conn, root, country=country, ttl_hours=ttl)
        except store_api.StoreAPIError as exc:
            print(f'  (skip "{root}": {exc})')
            continue
        for position, suggestion in enumerate(suggestions, 1):
            phrase = _clean(suggestion)
            if not phrase:
                continue
            entry = hits.setdefault(phrase, {'position': position, 'roots': set()})
            entry['position'] = min(entry['position'], position)
            entry['roots'].add(root)
        if deep and suggestions and _clean(suggestions[0]) not in seen_roots:
            queue.append(_clean(suggestions[0]))

    from_competitors = competitor_phrases(ws, conn, country, ttl)
    for phrase, apps in from_competitors.items():
        entry = hits.setdefault(phrase, {'position': 14, 'roots': set()})
        entry.setdefault('apps', set()).update(apps)
    for phrase, apps in from_competitors.items():
        hits[phrase].setdefault('apps', set()).update(apps)

    candidates, seeds = [], []
    for phrase, entry in hits.items():
        words = [w for w in tokens(phrase) if w not in strategy.phrase_stopwords]
        if not words:
            continue
        if len(words) < MIN_WORDS:
            if words[0] not in indexed and words[0] not in GENERIC_WORDS:
                seeds.append({'term': words[0], 'position': entry['position'],
                              'reason': 'a one-word query from the autocomplete'})
            continue
        if len(words) > MAX_WORDS or phrase in have:
            continue
        if _looks_like_an_app_name(phrase, words):
            continue

        score = _score_from_position(entry['position'])
        reasons = [f'autocomplete #{entry["position"]}'] if entry['position'] <= 12 else []
        if len(entry['roots']) > 1:
            score += 1
            reasons.append(f'{len(entry["roots"])} roots')
        apps = entry.get('apps') or set()
        if apps:
            score += 1
            reasons.append(f'in the title of {", ".join(sorted(apps)[:2])}')
        if len(words) >= 4:
            score -= 1
            reasons.append('long tail')
        weak = sorted(set(words) & strategy.low_value_terms)
        if weak:
            # The store ignores these words, or it does not allow them, so the
            # phrase can never match in full.
            score -= 2
            reasons.append(f'low value: {", ".join(weak)}')
        risky = sorted(set(words) & strategy.trademark_terms)
        if risky:
            score -= 2
            reasons.append(f'trademark: {", ".join(risky)}')
        covered_by, missing, nearest = coverage(phrase, group_locales,
                                                strategy.phrase_stopwords)
        if covered_by:
            score += 0.5
            reasons.append(f'already covered by {covered_by}')
        candidates.append({
            'phrase': phrase,
            'score': max(1, min(10, int(round(score)))),
            'position': entry['position'],
            'covered_by': covered_by,
            'missing': missing,
            'nearest': nearest,
            'risky': risky,
            'reasons': reasons,
        })

    if with_reviews:
        for word, count in sorted(review_words(ws, conn,
                                               ws.config.review_countries, ttl).items(),
                                  key=lambda item: -item[1]):
            if count >= 3 and word not in indexed:
                seeds.append({'term': word, 'position': 99,
                              'reason': f'{count} reviews use this word'})

    candidates.sort(key=lambda row: (-row['score'], row['position'], row['phrase']))
    unique_seeds, seen = [], set()
    for seed in sorted(seeds, key=lambda row: row['position']):
        if seed['term'] not in seen:
            seen.add(seed['term'])
            unique_seeds.append(seed)
    return candidates[:limit], unique_seeds[:limit]


# -- printing -----------------------------------------------------------------

def print_report(candidates, seeds, group_label=''):
    if not candidates and not seeds:
        print('\nThe autocomplete returned nothing for these roots.\n'
              'That answer is itself a finding: this market does not search your '
              'category with those words. Try roots in the local language, or another '
              'country with --country.')
        return
    if candidates:
        print(f'\n== Proposed target phrases{f" ({group_label})" if group_label else ""} ==\n')
        print(f'  {"score":>5}  {"phrase":<42} {"coverage":<26} why')
        for row in candidates:
            if row['covered_by']:
                state = f'covered by {row["covered_by"]}'
            else:
                state = f'needs {"+".join(row["missing"])} ({row["nearest"]})'
            print(f'  {row["score"]:>5}  {row["phrase"]:<42} {state:<26} '
                  f'{"; ".join(row["reasons"])}')
    if seeds:
        print('\n== Single words worth a keyword slot ==\n')
        for seed in seeds:
            print(f'  {seed["term"]:<24} {seed["reason"]}')
    print('\nA phrase matches only when ONE localization holds every word of it.\n'
          '"needs …" names the words to add, and the localization that is nearest.\n'
          'Write your choice into strategy.yaml with `aso phrases --write`, then run\n'
          '`aso audit` to see the gaps and `aso rank` to measure the position.')


# -- writing back into strategy.yaml ------------------------------------------

def render_entries(entries, key_name):
    """A YAML list block, indented for a top-level key."""
    documents = []
    for item in entries:
        row = {key_name: item[0], 'score': int(item[1])}
        if item[2]:
            row['why'] = item[2]
        documents.append(row)
    text = yaml.safe_dump(documents, sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=200)
    return ''.join(f'  {line}\n' if line.strip() else '\n'
                   for line in text.splitlines())


def merge_into_strategy(path, key, entries, key_name):
    """Replace the `key:` block of a strategy file with `entries`.

    The rest of the file, comments included, stays as it is. Comments inside
    the replaced block are lost, which is why the function returns the text
    that it wrote.
    """
    path = Path(path)
    original = path.read_text(encoding='utf-8') if path.is_file() else ''
    lines = original.splitlines(keepends=True)
    block = f'{key}:\n' + render_entries(entries, key_name)

    start = None
    for index, line in enumerate(lines):
        if re.match(rf'^{re.escape(key)}\s*:', line):
            start = index
            break
    if start is None:
        stamp = time.strftime('%Y-%m-%d', time.gmtime())
        suffix = '' if original.endswith('\n') or not original else '\n'
        path.write_text(f'{original}{suffix}\n# Added by `aso phrases` on {stamp}.\n{block}',
                        encoding='utf-8')
        return block

    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.startswith((' ', '\t', '#')):
            break
        end += 1
    # Keep the comment lines that sit at the end of the block: they belong to
    # the next key, not to this one.
    while end - 1 > start and lines[end - 1].lstrip().startswith('#'):
        end -= 1
    path.write_text(''.join(lines[:start]) + block + ''.join(lines[end:]), encoding='utf-8')
    return block


def write_phrases(ws, candidates, minimum_score=6):
    """Merge the proposals into `phrase_targets`, and keep what is there."""
    chosen = [(row['phrase'], row['score'], '') for row in candidates
              if row['score'] >= minimum_score]
    if not chosen:
        return [], ''
    existing = [(p, s, w) for p, s, w in ws.strategy.phrase_targets]
    have = {p.lower() for p, _s, _w in existing}
    added = [row for row in chosen if row[0].lower() not in have]
    if not added:
        return [], ''
    block = merge_into_strategy(ws.strategy_path, 'phrase_targets', existing + added,
                                'phrase')
    return added, block


def write_seeds(ws, seeds, score=5):
    """Merge the one-word proposals into `seed_keywords`."""
    existing = [(t, s, w) for t, s, w in ws.strategy.seed_keywords]
    have = {t.lower() for t, _s, _w in existing}
    added = [(seed['term'], score, seed['reason']) for seed in seeds
             if seed['term'].lower() not in have]
    if not added:
        return [], ''
    block = merge_into_strategy(ws.strategy_path, 'seed_keywords', existing + added,
                                'term')
    return added, block
