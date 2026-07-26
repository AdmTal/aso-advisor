"""`aso status`: where this app stands, in one screen.

The command answers the questions that you would otherwise need five commands
for. It works offline. With `--online` it also asks App Store Connect which
version is live, and whether the workspace matches it.
"""

import contextlib
from datetime import datetime, timezone

from . import assets, compare, db, loader
from .color import paint
from .color import severity as paint_severity
from .model import SEVERITIES


def _age(stamp):
    """A short age such as '4h' or '3d', from a stored timestamp."""
    if not stamp:
        return ''
    try:
        then = datetime.strptime(stamp, db.TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return ''
    seconds = (datetime.now(timezone.utc) - then).total_seconds()
    if seconds < 3600:
        return f'{int(seconds // 60)}m ago'
    if seconds < 86400:
        return f'{int(seconds // 3600)}h ago'
    return f'{int(seconds // 86400)}d ago'


def _row(label, value):
    return f'  {label:<11} {value}'


def unpushed_changes(ws, conn, version_name, local):
    """The fields that differ from the last pull or push of this version."""
    remembered, stamp, source = db.load_sync_snapshot(conn, version_name)
    if not remembered:
        return [], stamp, source
    return compare.diff_locales(local, remembered), stamp, source


def collect(ws, online=False, client=None):
    """Build the lines of the report."""
    lines = []
    add = lines.append
    app = ws.config.app

    add(_row('workspace', ws.root))
    identity = app.name or '(no name)'
    if app.track_id:
        identity += f'  ·  id {app.track_id}'
    add(_row('app', identity))

    versions = loader.discover_versions(ws.versions_dir)
    if not versions:
        add(_row('metadata', paint('no version yet — see docs/workspace.md', 'yellow')))
        return lines
    version_name, version_path = versions[-1]
    local = {}
    with contextlib.suppress(loader.MetadataError):
        local = loader.load_version_raw(version_path)
    asset_rows = assets.summary(version_path / 'assets')
    asset_count = sum(count for _c, _k, _d, count in asset_rows)
    add(_row('metadata', f'{version_name} (newest of {len(versions)})  ·  '
                         f'{len(local)} locale(s)  ·  {asset_count} asset(s)'))

    conn = db.connect(ws.db_path)
    try:
        changes, stamp, source = unpushed_changes(ws, conn, version_name, local)
        if changes:
            locale_count, field_count = compare.summarize(changes)
            add(_row('unpushed', paint(
                f'{field_count} field(s) in {locale_count} locale(s) changed since the '
                f'last {source or "sync"} ({_age(stamp)})', 'yellow')))
            for change in changes[:5]:
                add(f'              {change.locale} {change.field}')
            if len(changes) > 5:
                add(f'              … and {len(changes) - 5} more')
        elif stamp:
            add(_row('unpushed', f'nothing — the workspace matches the last '
                                 f'{source} ({_age(stamp)})'))
        else:
            add(_row('unpushed', 'unknown — run `aso pull` or `aso push` one time'))

        runs = db.run_history(conn, limit=1)
        if runs:
            run = runs[0]
            counts = {}
            for row in db.list_suggestions(conn, 'open'):
                counts[row['severity']] = counts.get(row['severity'], 0) + 1
            shown = '  '.join(paint_severity(sev, f'{sev.lower()}:{counts.get(sev, 0)}')
                              for sev in SEVERITIES if counts.get(sev))
            add(_row('audit', f'run #{run["id"]} {_age(run["ts"])}  ·  '
                              f'{sum(counts.values())} open   {shown}'))
            if run['new_count'] or run['resolved_count']:
                add(f'              {run["new_count"]} new, '
                    f'{run["resolved_count"]} resolved in that run')
        else:
            add(_row('audit', paint('never — run `aso audit`', 'yellow')))

        ranks = db.rank_summary(conn)
        if ranks:
            movers = [r for r in ranks if r['prev'] and r['rank']]
            best = min(movers, key=lambda r: r['rank'] - r['prev'], default=None)
            found = sum(1 for r in ranks if r['rank'])
            line = (f'{len(ranks)} term(s), {found} in the results  ·  last check '
                    f'{_age(ranks[0]["ts"])}')
            add(_row('ranks', line))
            if best and best['rank'] != best['prev']:
                delta = best['prev'] - best['rank']
                arrow = f'▲ +{delta}' if delta > 0 else f'▼ {delta}'
                colour = 'green' if delta > 0 else 'red'
                add(f'              {paint(arrow, colour)} {best["term"]} '
                    f'({best["country"]}) → #{best["rank"]}')
        else:
            add(_row('ranks', 'never — run `aso rank`'))

        cached = conn.execute('SELECT COUNT(*) AS n FROM api_cache').fetchone()['n']
        add(_row('cache', f'{cached} stored answer(s), kept {ws.config.cache_hours}h'))
    finally:
        conn.close()

    add(_row('key', _key_state(ws)))

    if online:
        lines.extend(_online(ws, version_name, local, client))
    lines.append('')
    lines.extend(_next_steps(ws, versions, local))
    return lines


def _key_state(ws):
    from .asc.client import ASCAuthError, Credentials

    try:
        creds = Credentials.resolve(ws)
    except ASCAuthError:
        return 'none — `aso auth` explains how to make one (pull and push need it)'
    return f'key {creds.key_id} — `aso auth --check` confirms it'


def _online(ws, version_name, local, client=None):
    from .asc.client import ASCAuthError, ASCClient, ASCError, Credentials
    from .asc.pull import collect as pull_collect

    lines = ['']
    try:
        client = client or ASCClient(Credentials.resolve(ws))
        live_version, remote = pull_collect(client, quiet=True)
    except (ASCAuthError, ASCError) as exc:
        lines.append(_row('store', paint(f'not reachable: '
                                         f'{str(exc).splitlines()[0]}', 'red')))
        return lines
    lines.append(_row('store', f'live version {live_version}, {len(remote)} locale(s)'))
    if live_version != version_name:
        lines.append(_row('', paint(f'the newest local version is {version_name}',
                                    'yellow')))
    changes = compare.diff_locales(local, remote)
    if changes:
        locale_count, field_count = compare.summarize(changes)
        lines.append(_row('drift', paint(
            f'{field_count} field(s) in {locale_count} locale(s) differ from the store '
            '— `aso pull --check` shows them', 'yellow')))
    else:
        lines.append(_row('drift', 'none — the workspace matches the store'))
    return lines


def _next_steps(ws, versions, local):
    """One or two things that are worth doing now."""
    steps = []
    if not ws.strategy.phrase_targets:
        steps.append('aso phrases            propose the target search phrases')
    if not ws.strategy.brand_phrases:
        steps.append('edit strategy.yaml     add brand_phrases so branded search works')
    if not local:
        steps.append('aso pull               read the live metadata into the workspace')
    if not steps:
        steps.append('aso audit              the newest version')
        steps.append('aso rank               where you stand today')
    return ['next:'] + [f'  {step}' for step in steps[:3]]


def cmd_status(ws, online=False, client=None):
    for line in collect(ws, online=online, client=client):
        print(line)
    return 0
