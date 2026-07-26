"""The report: Markdown for the file, a short summary for the terminal.

Report files use a Unix timestamp in the name:

    reports/aso-report-1753574400.md

A timestamp keeps the files unique and in order. Two runs in the same day do
not overwrite each other.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import rules
from .color import paint
from .color import severity as paint_severity
from .model import SEVERITIES

SEV_ICON = {'CRITICAL': '🟥', 'HIGH': '🟧', 'MEDIUM': '🟨', 'LOW': '⬜', 'INFO': 'ℹ️'}

EVERGREEN_CHECKLIST = """\
You cannot audit these points from the files in a repository, but they are the
strongest levers in App Store search today. Check them every quarter.

- **Custom Product Pages appear in organic search.** You can link terms from
  your keyword field to a specific page in App Store Connect, and the store
  serves that page for those searches. Most apps do not use custom pages at
  all, so this is cheap differentiation.
- **Assistants recommend apps from plain descriptions.** Large language models
  read your description and your reviews. Say what the app does in literal
  words in the first paragraph.
- **The store indexes the text in your screenshot captions.** Put real search
  phrases in the captions, not slogans.
- **Apple makes the discovery tags from your metadata.** The description feeds
  them. Keep the opening literal.
- **Rating recency has weight.** Ask for a review after a success moment. Reset
  the rating only for a major change of the app.
- **In-app events match search queries.** They are cheap extra reach.
- **Retention after install is a ranking input.** Keyword wins go away if the
  users leave on day one. Pair each ASO push with an onboarding fix.
- **Watch the metadata of the competitors.** A title change by a strong app in
  your category usually shows a keyword that is worth a check.
  Use `aso competitors`.
- **Autocomplete order is the popularity order of Apple.** Mine it again after
  each iOS release season. Use `aso discover`.
"""


def _counts(suggestions):
    counts = dict.fromkeys(SEVERITIES, 0)
    for s in suggestions:
        if s.status == 'open':
            counts[s.severity] += 1
    return counts


def render_markdown(ctx, run_id, suggestions, stats, app_name='', rank_rows=None,
                    asset_rows=None, timestamp=None):
    """Make the Markdown body of the report."""
    stamp = timestamp or int(time.time())
    when = datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    open_items = [s for s in suggestions if s.status == 'open']
    counts = _counts(suggestions)
    lines = []
    add = lines.append

    title = f'ASO Advisor report — {app_name} ' if app_name else 'ASO Advisor report — '
    add(f'# {title}metadata {ctx.version}')
    add('')
    add(f'Run #{run_id} · {when} · timestamp `{stamp}`')
    add('')
    add(f'**{stats["open"]} open suggestions** — {stats["new"]} new, '
        f'{stats["regressed"]} regressed, {len(stats["resolved"])} resolved since the '
        'run before.')
    add('')
    add('| Severity | Open |')
    add('|---|---|')
    for sev in SEVERITIES:
        add(f'| {SEV_ICON[sev]} {sev} | {counts[sev]} |')
    add('')

    if stats['resolved']:
        add('## ✅ Resolved since the run before')
        add('')
        for r in stats['resolved']:
            add(f'- ~~{r["title"]}~~')
        add('')

    add('## Action list (strongest impact first)')
    add('')
    if not open_items:
        add('Nothing is open. The metadata passes every rule that is active.')
        add('')
    for sev in SEVERITIES:
        batch = [s for s in open_items if s.severity == sev]
        if not batch:
            continue
        add(f'### {SEV_ICON[sev]} {sev}')
        add('')
        for s in batch:
            flags = ' **[NEW]**' if s.is_new else (' **[REGRESSED]**' if s.regressed else '')
            add(f'- `{s.fid}`{flags} **{s.title}**')
            if s.detail:
                for line in s.detail.splitlines():
                    add(f'  - {line}')
            if s.fix:
                add(f'  - 👉 _Fix: {s.fix}_')
        add('')

    matrix = rules.phrase_coverage_matrix(ctx)
    gids = [g for g in matrix if matrix[g]]
    if gids:
        add('## Long-tail phrase coverage per storefront')
        add('')
        add('A phrase ranks only when ONE localization of the storefront holds every '
            'word of it.')
        add('')
        add('| Phrase | ' + ' | '.join(ctx.group_name(g) for g in gids) + ' |')
        add('|---' * (len(gids) + 1) + '|')
        for index, (phrase, score, *_rest) in enumerate(matrix[gids[0]]):
            cells = []
            for gid in gids:
                _p, _s, covered_by, missing, nearest = matrix[gid][index]
                cells.append(f'✅ {covered_by}' if covered_by
                             else f'❌ needs {"+".join(missing)} ({nearest})')
            add(f'| {phrase} ({score}) | ' + ' | '.join(cells) + ' |')
        add('')

    proposals = rules.propose_keyword_lines(ctx)
    if proposals:
        add(f'## Proposed keyword fields ({ctx.group_name(ctx.primary_group)} storefront)')
        add('')
        add('The proposal is deterministic. It fills the free characters with your best '
            'uncovered seeds, then exchanges the weakest terms. Read it before you use it.')
        add('')
        for code, old, new, changed in proposals:
            add(f'**{code}** ({", ".join(changed)})')
            add('```diff')
            add(f'- {old}')
            add(f'+ {new}')
            add('```')
        add('')

    if rank_rows:
        add('## Live search ranks (last `aso rank` check)')
        add('')
        add('| Term | Country | Rank | Before | When |')
        add('|---|---|---|---|---|')
        for r in rank_rows:
            current = f'#{r["rank"]}' if r['rank'] else '—'
            before = f'#{r["prev"]}' if r['prev'] else '—'
            add(f'| {r["term"]} | {r["country"]} | {current} | {before} | {r["ts"][:10]} |')
        add('')
        add('Run `aso rank` for new data. The tool caches the answers of Apple for 12 hours.')
        add('')

    if asset_rows:
        add('## Localized assets in this version')
        add('')
        add('| Locale | Kind | Device | Files |')
        add('|---|---|---|---|')
        for code, kind, device, count in asset_rows:
            add(f'| {code} | {kind} | {device} | {count} |')
        add('')

    add('## Evergreen checklist')
    add('')
    add(EVERGREEN_CHECKLIST)
    add('')
    add('---')
    add('Manage the items: `aso list` · `aso show S-xxxxxxxx` · '
        '`aso dismiss S-xxxxxxxx "reason"` · `aso reopen S-xxxxxxxx`.')
    add('A dismissed item stays quiet in the next runs. A fixed item resolves by itself.')
    return '\n'.join(lines)


def report_path(reports_dir, timestamp=None, suffix='md'):
    """A unique path with a Unix timestamp in the name."""
    stamp = timestamp or int(time.time())
    path = Path(reports_dir) / f'aso-report-{stamp}.{suffix}'
    counter = 2
    while path.exists():
        path = Path(reports_dir) / f'aso-report-{stamp}-{counter}.{suffix}'
        counter += 1
    return path


def write_report(markdown, reports_dir, timestamp=None):
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    path = report_path(reports_dir, timestamp)
    path.write_text(markdown, encoding='utf-8')
    return path


def render_json(ctx, run_id, suggestions, stats, app_name='', timestamp=None):
    stamp = timestamp or int(time.time())
    return json.dumps({
        'app': app_name,
        'metadata_version': ctx.version,
        'run': run_id,
        'timestamp': stamp,
        'generated_at': datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
        'counts': _counts(suggestions),
        'open': stats['open'],
        'new': stats['new'],
        'regressed': stats['regressed'],
        'resolved': stats['resolved'],
        'suggestions': [s.to_dict() for s in suggestions],
    }, indent=2, ensure_ascii=False)


def print_console(ctx, run_id, suggestions, stats, path=None):
    """The short summary for the terminal."""
    open_items = [s for s in suggestions if s.status == 'open']
    counts = _counts(suggestions)
    bar = '=' * 68
    print(bar)
    print(f' ASO ADVISOR — metadata {ctx.version} · run #{run_id}')
    print(bar)
    print(f' open: {stats["open"]}   new: {stats["new"]}   regressed: {stats["regressed"]}'
          f'   resolved: {len(stats["resolved"])}')
    print(' ' + '  '.join(paint_severity(s, f'{SEV_ICON[s]} {s}:{counts[s]}')
                          for s in SEVERITIES))
    print(bar)
    if stats['resolved']:
        print('\n ' + paint('✅ RESOLVED since the run before:', 'green'))
        for r in stats['resolved'][:10]:
            print(f'    - {r["title"]}')
    for sev in SEVERITIES:
        batch = [s for s in open_items if s.severity == sev]
        if not batch or sev == 'INFO':
            continue
        print(f'\n {paint_severity(sev, f"{SEV_ICON[sev]} {sev}")}')
        for s in batch:
            flag = ' [NEW]' if s.is_new else (' [REGRESSED]' if s.regressed else '')
            print(f'   {paint(s.fid, "dim")}{flag}  {s.title}')
            if s.fix and sev in ('CRITICAL', 'HIGH'):
                print('              ' + paint(f'→ {s.fix}', 'dim'))
    info = [s for s in open_items if s.severity == 'INFO']
    if info:
        print(f'\n ℹ️  {len(info)} note(s). The report file has them.')
    if path:
        print(f'\n Report: {path}')
    print(' Manage: aso list · aso show <id> · aso dismiss <id> "reason" · aso reopen <id>\n')
