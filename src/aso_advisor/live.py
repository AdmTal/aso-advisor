"""The live commands.

Each command reads the public endpoints of Apple through `store_api` and keeps
the history in the database of the workspace.

    rank          the real position of your app for your target phrases
    competitors   metadata and rating snapshots of the apps that you track
    discover      keyword ideas from the autocomplete of the App Store
    reviews       the words of your users, and the rating of the last 30 days
    verify-groups a live test of the cross-localization table
"""

import hashlib
from datetime import datetime, timedelta, timezone

from . import db, loader, store_api
from .model import tokens

# Words that carry no meaning for keyword mining.
REVIEW_STOPWORDS = frozenset('''
a about after all also an and any app apps are as at be been before but by
can cant could did do does dont even for from get got had has have he her
his i if im in into is it its just me more most my no not now of on only
or our over really she should so some than that the them then there they
this to too use used using very was we what when will with would you your
'''.split())


def latest_locales(ws):
    """The metadata of the newest version, or an empty dictionary."""
    versions = loader.discover_versions(ws.versions_dir)
    if not versions:
        return {}
    return loader.load_version(versions[-1][1])


def group_indexed_tokens(ws, locales, country):
    """Every token that the storefront group of `country` indexes."""
    gid = country.upper()
    groups = ws.config.groups()
    if gid not in groups:
        gid = ws.config.app.default_country.upper()
    if gid not in groups:
        gid = next(iter(groups), '')
    out = set()
    if gid:
        for code in groups[gid][1]:
            if code in locales:
                out |= locales[code].indexed_tokens
    return out, gid


def _arrow(previous, current):
    if previous is None:
        return 'new'
    if current is None:
        return f'lost (was #{previous})'
    if current < previous:
        return f'▲ +{previous - current}'
    if current > previous:
        return f'▼ -{current - previous}'
    return '='


def _ttl(ws, fresh):
    return 0 if fresh else ws.config.cache_hours


# -- rank ---------------------------------------------------------------------

def cmd_rank(ws, conn, countries=None, top=100, fresh=False):
    track_id = ws.require_track_id()
    ttl = _ttl(ws, fresh)
    countries = countries or ws.config.rank_countries
    terms = list(dict.fromkeys(
        list(ws.strategy.brand_phrases) + [p for p, _s, _w in ws.strategy.phrase_targets]))
    if not terms:
        print('No terms to check. Add `brand_phrases` or `phrase_targets` to '
              f'{ws.strategy_path}.')
        return

    print(f'{len(terms)} term(s) × {len(countries)} storefront(s), top {top} results each. '
          f'The tool caches the answers for {ws.config.cache_hours}h unless you use '
          '--fresh.\n')
    for country in countries:
        rows = []
        for term in terms:
            try:
                results = store_api.search(conn, term, country=country, limit=top,
                                           ttl_hours=ttl)
            except store_api.StoreAPIError as exc:
                print(f'  (skip "{term}" in {country}: {exc})')
                continue
            rank = store_api.rank_of(results, track_id)
            top3 = [[a.get('trackId'), (a.get('trackName') or '')[:40]] for a in results[:3]]
            previous, _ts = db.previous_rank(conn, term, country)
            db.record_rank(conn, term, country, rank, len(results), top3)
            rows.append((term, rank, previous, top3))
        if not rows:
            continue
        rows.sort(key=lambda r: r[1] if r[1] is not None else 999)
        print(f'== {country.upper()} ==')
        print(f'  {"term":<36} {"rank":>5}  {"move":<14} leader')
        for term, rank, previous, top3 in rows:
            shown = f'#{rank}' if rank else '—'
            leader = top3[0][1] if top3 else ''
            print(f'  {term:<36} {shown:>5}  {_arrow(previous, rank):<14} {leader}')
        found = sum(1 for _t, r, _p, _a in rows if r)
        print(f'  -> in the top {top} for {found}/{len(rows)} terms\n')
    print('The history is stored. The next `aso rank` shows the movement, and the audit\n'
          'report holds the last snapshot.')


# -- competitors --------------------------------------------------------------

def cmd_competitors(ws, conn, country=None, fresh=False, suggest=None, limit=15):
    ttl = _ttl(ws, fresh)
    country = country or ws.config.app.default_country

    if suggest:
        results = store_api.search(conn, suggest, country=country, limit=limit, ttl_hours=ttl)
        print(f'Top {len(results)} apps for "{suggest}" in {country.upper()}.\n'
              f'Copy the ones that you want into `competitors` in {ws.strategy_path}.\n')
        for position, app in enumerate(results, 1):
            print(f'  {position:>2}. {app.get("trackId")}  '
                  f'{(app.get("trackName") or "")[:52]:<52} '
                  f'⭐ {app.get("averageUserRating") or 0:.1f} '
                  f'({app.get("userRatingCount") or 0:,})')
        print('\nYAML shape:\n  competitors:\n    - track_id: 123456789\n      label: Name')
        return

    ids = list(ws.strategy.competitors)
    if ws.config.app.track_id:
        ids.append(ws.config.app.track_id)
    if not ids:
        print(f'No competitors yet. Add them to {ws.strategy_path}, or find them with:\n'
              '  aso competitors --suggest "your main search term"')
        return

    results = store_api.lookup(conn, track_ids=ids, country=country, ttl_hours=ttl)
    if not results:
        print('The lookup returned nothing. Check the identifiers, or check your network.')
        return
    baseline = db.last_competitor_id(conn)

    print(f'== Competitor watch ({country.upper()}) — {len(results)} apps ==\n')
    for app in sorted(results, key=lambda a: -(a.get('userRatingCount') or 0)):
        track_id = app.get('trackId')
        snap = {
            'track_id': track_id, 'country': country,
            'name': app.get('trackName', ''),
            'version': app.get('version', ''),
            'released': (app.get('currentVersionReleaseDate') or '')[:10],
            'rating': round(app.get('averageUserRating') or 0, 2),
            'rating_count': app.get('userRatingCount') or 0,
            'price': app.get('price') or 0.0,
            'desc_hash': hashlib.sha1((app.get('description') or '').encode()).hexdigest()[:12],
        }
        db.record_competitor(conn, snap)
        previous = db.previous_competitor(conn, track_id, country, baseline + 1)

        mark = ' ★ (your app)' if track_id == ws.config.app.track_id else ''
        print(f'{snap["name"]}{mark}')
        print(f'   ⭐ {snap["rating"]} ({snap["rating_count"]:,})   v{snap["version"]} '
              f'({snap["released"]})   {snap["price"]}')
        if previous:
            for note in _competitor_notes(previous, snap):
                print(f'   • {note}')
        print()
    print('The snapshots are stored. Run this every week. A title change or a new '
          'description is the signal.')


def _competitor_notes(previous, snap):
    notes = []
    if previous['name'] != snap['name']:
        notes.append(f'TITLE CHANGED: "{previous["name"]}" → "{snap["name"]}"  ← strong signal')
    if previous['version'] != snap['version']:
        notes.append(f'new version {previous["version"]} → {snap["version"]}')
    if previous['desc_hash'] != snap['desc_hash']:
        notes.append('the description changed (discovery tags or conversion push)')
    delta = snap['rating_count'] - (previous['rating_count'] or 0)
    if delta:
        try:
            then = datetime.strptime(previous['ts'], db.TS_FORMAT).replace(tzinfo=timezone.utc)
            days = max(1, (datetime.now(timezone.utc) - then).days)
            notes.append(f'+{delta:,} ratings since {previous["ts"][:10]} '
                         f'(about {delta / days:.1f} per day)')
        except ValueError:
            notes.append(f'+{delta:,} ratings since the snapshot before')
    return notes


# -- discover -----------------------------------------------------------------

def cmd_discover(ws, conn, country=None, deep=False, fresh=False):
    ttl = _ttl(ws, fresh)
    country = (country or ws.config.app.default_country).lower()
    locales = latest_locales(ws)
    indexed, group_label = group_indexed_tokens(ws, locales, country)

    roots = list(ws.strategy.discovery_seeds)
    roots += list(ws.strategy.local_discovery_seeds.get(country, []))
    if not roots:
        print(f'No seeds to expand. Add `discovery_seeds` to {ws.strategy_path}.')
        return

    best = {}      # suggestion -> (best position, source seed)
    print(f'{len(roots)} seed term(s) through the App Store autocomplete '
          f'({country.upper()}{", deep" if deep else ""})…\n')
    seen = set()
    while roots:
        root = roots.pop(0)
        if root in seen:
            continue
        seen.add(root)
        try:
            suggestions = store_api.hints(conn, root, country=country, ttl_hours=ttl)
        except store_api.StoreAPIError as exc:
            print(f'  (skip "{root}": {exc})')
            continue
        for position, term in enumerate(suggestions, 1):
            if term not in best or position < best[term][0]:
                best[term] = (position, root)
        if deep and suggestions and suggestions[0] not in seen:
            roots.append(suggestions[0])

    if not best:
        print('The autocomplete returned nothing for these seeds.\n'
              'That answer is a finding: users of this storefront do not search these '
              'words. A translated keyword field for those queries spends characters on '
              'nothing.')
        return

    rows = []
    for term, (position, source) in best.items():
        words = [w for w in tokens(term) if w not in ws.strategy.phrase_stopwords]
        missing = [w for w in words if w not in indexed]
        rows.append((position, term, missing, source))
    rows.sort(key=lambda r: (len(r[2]) == 0, r[0]))

    print(f'{len(rows)} unique suggestions. GAP marks the words that no localization of '
          f'the {group_label} group indexes.\n')
    print(f'  {"pos":>3}  {"suggestion":<46} {"status":<28} from')
    for position, term, missing, source in rows:
        status = f'GAP: {"+".join(missing)}' if missing else 'covered'
        print(f'  {position:>3}  {term:<46} {status:<28} {source}')
    print('\nPosition 1 is the completion with the most searches. A GAP with a low\n'
          'position number is your best new keyword. Put the missing words into\n'
          'seed_keywords or phrase_targets in your strategy file, then run `aso audit`.')


# -- verify-groups ------------------------------------------------------------

def cmd_verify_groups(ws, conn, group=None, top=200, fresh=False):
    """Test that the secondary localizations of a group really index there.

    The command searches "<unique token> <anchor>" for tokens that live in
    exactly one keyword field of the group. It also searches control tokens
    that no localization holds. If the app ranks for the unique tokens and not
    for the controls, the group is correct.
    """
    track_id = ws.require_track_id()
    ttl = _ttl(ws, fresh)
    groups = ws.config.groups()
    gid = (group or ws.config.app.default_country).upper()
    if gid not in groups:
        print(f'Unknown storefront group {gid!r}. Known groups: {", ".join(sorted(groups))}')
        return
    anchor = ws.strategy.probe_anchor
    if not anchor:
        print('Set `probe.anchor` in your strategy file first. Use the main category '
              'phrase of your app, for example "screen recorder".')
        return

    locales = latest_locales(ws)
    label, codes = groups[gid]
    country = gid.lower()

    carriers = {}
    for code in codes:
        meta = locales.get(code)
        if meta is None or meta.is_non_spaced:
            continue
        for entry in meta.kw_entries:
            for token in tokens(entry):
                carriers.setdefault(token, set()).add(code)

    print(f'== verify-groups: {label} ({country}) — expected localizations {codes} ==\n')
    print('The tool reads the newest YAML version. The result means something only if\n'
          'that version is the version that is live on the store.\n')
    for code in codes:
        uniques = [t for t, holders in carriers.items()
                   if holders == {code} and t.isascii() and len(t) > 3][:2]
        if not uniques:
            print(f'  {code}: no unique probe token available — skipped')
            continue
        for token in uniques:
            results = store_api.search(conn, f'{token} {anchor}', country=country,
                                       limit=top, ttl_hours=ttl)
            rank = store_api.rank_of(results, track_id)
            verdict = f'INDEXED (#{rank})' if rank else f'not in the top {len(results)}'
            print(f'  {code}: "{token} {anchor}" -> {verdict}')
    for token in ws.strategy.probe_controls:
        results = store_api.search(conn, f'{token} {anchor}', country=country,
                                   limit=top, ttl_hours=ttl)
        rank = store_api.rank_of(results, track_id)
        flag = f'⚠️ ranked #{rank} — the probe is not reliable today' if rank else 'absent ✓'
        print(f'  control: "{token} {anchor}" -> {flag}')
    print('\nA localization whose unique tokens rank, while the controls do not, indexes\n'
          'in this storefront. Run this test every quarter. Apple has changed the group\n'
          'membership before.')


# -- reviews ------------------------------------------------------------------

def cmd_reviews(ws, conn, countries=None, pages=3, fresh=False):
    track_id = ws.require_track_id()
    ttl = _ttl(ws, fresh)
    countries = countries or ws.config.review_countries
    locales = latest_locales(ws)
    indexed, _gid = group_indexed_tokens(ws, locales, ws.config.app.default_country)

    all_reviews = []
    for country in countries:
        found = store_api.reviews(conn, track_id, country=country, pages=pages, ttl_hours=ttl)
        all_reviews.extend(found)
        print(f'  {country.upper()}: {len(found)} recent reviews')
    if not all_reviews:
        print('\nNo reviews on the storefronts that you checked. Small storefronts often '
              'have none.')
        return

    distribution = dict.fromkeys(range(1, 6), 0)
    cut = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')
    recent = []
    for review in all_reviews:
        distribution[review['rating']] += 1
        if review['date'] >= cut:
            recent.append(review)
    average = sum(r['rating'] for r in all_reviews) / len(all_reviews)
    print(f'\n== Rating pulse ({len(all_reviews)} recent reviews) ==')
    print('  ' + '  '.join(f'{i}★:{distribution[i]}' for i in range(5, 0, -1))
          + f'   average {average:.2f}')
    if recent:
        recent_average = sum(r['rating'] for r in recent) / len(recent)
        warning = '⚠️ below the overall average' if recent_average < average - 0.3 else ''
        print(f'  last 30 days: {len(recent)} reviews, average {recent_average:.2f} {warning}')

    counts = {}
    for review in all_reviews:
        for word in set(tokens(review['title'] + ' ' + review['body'])):
            if len(word) < 3 or word in REVIEW_STOPWORDS:
                continue
            counts[word] = counts.get(word, 0) + 1
    gaps = sorted(((n, w) for w, n in counts.items() if n >= 3 and w not in indexed),
                  reverse=True)[:20]
    if gaps:
        print('\n== Words of your users that you do NOT index (3 reviews or more) ==')
        print('  ' + ', '.join(f'{w}({n})' for n, w in gaps))
        print('  Users search with the words that they write. Take the good ones as seeds.')

    bad = [r for r in all_reviews if r['rating'] <= 3][:8]
    if bad:
        print('\n== Recent reviews of 3★ or less (fix list and reply list) ==')
        for review in bad:
            print(f'  {review["rating"]}★ {review["date"]} [{review["country"]}] '
                  f'v{review["version"]} — {review["title"][:70]}')
    print('\nRating recency is a ranking input. Answer the negative reviews, and ask for a '
          'review after a success moment.')
