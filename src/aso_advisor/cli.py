"""The command-line interface.

Run `aso --help` for the list of commands, or read `docs/commands.md`.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from . import (
    __version__,
    assets,
    db,
    live,
    loader,
    phrases,
    report,
    rules,
    scaffold,
    workspace,
)
from .model import SEVERITIES
from .workspace import WorkspaceError

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FINDINGS = 2

EPILOG = """\
examples:
  aso init --app-id 123456789     make a workspace from your live App Store page
  aso auth                        check the App Store Connect key, or learn to make one
  aso pull                        read the live metadata into the workspace
  aso audit                       audit the newest metadata version
  aso audit --fail-on high        the same, with an exit code for a build pipeline
  aso phrases                     propose the target search phrases
  aso list                        the open suggestions
  aso dismiss S-1a2b3c4d "bet"    hide one suggestion and say why
  aso rank                        the real search position of your target phrases
  aso push --dry-run              show what a metadata push would change
  aso push-assets                 upload the localized screenshots and videos

documentation: https://github.com/AdmTal/aso-advisor/tree/main/docs
"""


# -- helpers ------------------------------------------------------------------

def _load(args):
    return workspace.load(explicit=getattr(args, 'workspace', None))


def _open_db(ws, args):
    if getattr(args, 'no_state', False):
        return db.connect_memory()
    return db.connect(ws.db_path)


def _split_list(raw):
    return [item.strip().lower() for item in (raw or '').split(',') if item.strip()]


def _build_context(ws, version_name=None):
    """Load a metadata version and make the rule context."""
    versions = loader.discover_versions(ws.versions_dir)
    name, path = loader.select_version(versions, version_name)
    locales = loader.load_version(path)
    prev_name, prev_path = loader.previous_version(versions, name)
    prev_locales = loader.load_version(prev_path) if prev_path else {}
    ctx = rules.RuleContext(
        locales=locales,
        strategy=ws.strategy,
        groups=ws.config.groups(),
        primary_locale=ws.config.app.primary_locale,
        default_country=ws.config.app.default_country,
        version=name,
        prev_locales=prev_locales,
        prev_version=prev_name or '',
    )
    return ctx, path


# -- init ---------------------------------------------------------------------

def cmd_init(args):
    root = Path(args.path) if args.path else Path.cwd() / workspace.DEFAULT_DIRNAME
    identity = {}
    track_id = scaffold.parse_app_id(args.app_id)
    if track_id or args.bundle_id:
        print('Reading the public App Store data…')
        identity = scaffold.fetch_identity(track_id=track_id, bundle_id=args.bundle_id or '',
                                           country=args.country)
        if identity:
            print(f'  Found: {identity["name"]} (id {identity["track_id"]}, '
                  f'{identity["bundle_id"]})')
        else:
            print('  Nothing found. The tool writes an empty workspace instead.')
            identity = {'track_id': track_id, 'bundle_id': args.bundle_id or ''}

    try:
        written = scaffold.create(root, identity=identity, primary_locale=args.locale,
                                  country=args.country, version=args.metadata_version,
                                  force=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    print(f'\nWorkspace: {root}')
    for path in written:
        print(f'  + {path.relative_to(root.parent)}')
    print(f"""
Next steps:

  1. Put your live metadata into {root.name}/versions/{args.metadata_version or
                                                       identity.get('version', '1.0')}/.
     One block per locale. See {root.name}/README.md.
  2. Write your strategy in {root.name}/strategy.yaml: brand, seeds, phrases.
  3. Run:  aso audit

The getting-started guide has the full walk-through:
https://github.com/AdmTal/aso-advisor/blob/main/docs/getting-started.md
""")
    return EXIT_OK


# -- audit --------------------------------------------------------------------

def cmd_audit(args):
    ws = _load(args)
    ctx, version_path = _build_context(ws, args.metadata_version)

    findings = rules.run_all(ctx, disabled=ws.config.disabled_rules)
    asset_rows = []
    if ws.config.assets.check and not args.no_assets:
        assets_dir = version_path / 'assets'
        findings.extend(assets.audit(assets_dir, ctx.locales, ws.config.assets,
                                     ws.config.app.primary_locale))
        asset_rows = assets.summary(assets_dir)
    if ws.config.disabled_rules:
        findings = [s for s in findings if s.rule not in ws.config.disabled_rules]
    findings.sort(key=lambda s: (s.severity_rank, s.scope, s.title))

    conn = _open_db(ws, args)
    run_id = db.start_run(conn, ctx.version)
    stats = db.reconcile(conn, run_id, findings)
    db.save_snapshots(conn, run_id, ctx.version, ctx.locales)
    rank_rows = db.rank_summary(conn)
    visible = [s for s in findings if s.status != 'dismissed']
    stamp = int(time.time())

    path = None
    if not args.no_report:
        markdown = report.render_markdown(ctx, run_id, visible, stats,
                                          app_name=ws.config.app.name,
                                          rank_rows=rank_rows, asset_rows=asset_rows,
                                          timestamp=stamp)
        path = report.write_report(markdown, ws.reports_dir, timestamp=stamp)

    if args.json:
        print(report.render_json(ctx, run_id, visible, stats,
                                 app_name=ws.config.app.name, timestamp=stamp))
    else:
        report.print_console(ctx, run_id, visible, stats, path)
        hidden = sum(1 for s in findings if s.status == 'dismissed')
        if hidden:
            print(f' ({hidden} dismissed suggestion(s) are hidden. '
                  'Use `aso list --all` to see them.)\n')
    conn.close()

    if args.fail_on and args.fail_on != 'none':
        threshold = SEVERITIES.index(args.fail_on.upper())
        blocking = [s for s in visible if s.status == 'open' and s.severity_rank <= threshold]
        if blocking:
            print(f'{len(blocking)} suggestion(s) at {args.fail_on.upper()} or above.',
                  file=sys.stderr)
            return EXIT_FINDINGS
    return EXIT_OK


# -- suggestion lifecycle -----------------------------------------------------

def cmd_list(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    rows = db.list_suggestions(conn, 'all' if args.all else 'open')
    if args.severity:
        wanted = {s.upper() for s in _split_list(args.severity)}
        rows = [r for r in rows if r['severity'] in wanted]
    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2, ensure_ascii=False))
        conn.close()
        return EXIT_OK
    if not rows:
        print('Nothing to show. Run `aso audit` first.')
        conn.close()
        return EXIT_OK
    for row in rows:
        state = '' if row['status'] == 'open' else f' [{row["status"]}]'
        print(f'{row["fid"]}  {row["severity"]:<8} {row["scope"]:<10}{state}  {row["title"]}')
    conn.close()
    return EXIT_OK


def cmd_show(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    row = db.get_suggestion(conn, args.fid)
    if row is None:
        print(f'No suggestion {args.fid}. Use `aso list` to see the identifiers.',
              file=sys.stderr)
        conn.close()
        return EXIT_ERROR
    print(f'{row["fid"]}  [{row["severity"]}] [{row["status"]}]  scope={row["scope"]}  '
          f'rule={row["rule"]}')
    print(f'\n{row["title"]}\n')
    if row['detail']:
        print(row['detail'] + '\n')
    if row['fix']:
        print(f'Fix: {row["fix"]}')
    if row['note']:
        print(f'Note: {row["note"]}')
    print(f'First seen in run #{row["first_seen"]}, last seen in run #{row["last_seen"]}.')
    conn.close()
    return EXIT_OK


def _set_status(args, status):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    ok = db.set_status(conn, args.fid, status, getattr(args, 'reason', '') or '')
    conn.close()
    if not ok:
        print(f'No suggestion {args.fid}.', file=sys.stderr)
        return EXIT_ERROR
    print(f'{args.fid} → {status}')
    return EXIT_OK


def cmd_history(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    rows = db.run_history(conn)
    conn.close()
    if not rows:
        print('No run yet.')
        return EXIT_OK
    print(f'{"run":>4}  {"when":<22} {"metadata":<10} {"open":>5} {"new":>4} {"resolved":>9}')
    for row in rows:
        print(f'{row["id"]:>4}  {row["ts"]:<22} {row["version"]:<10} {row["open_count"]:>5} '
              f'{row["new_count"]:>4} {row["resolved_count"]:>9}')
    return EXIT_OK


# -- metadata versions --------------------------------------------------------

def cmd_versions(args):
    ws = _load(args)
    versions = loader.discover_versions(ws.versions_dir)
    if not versions:
        print(f'No version in {ws.versions_dir}.')
        return EXIT_OK
    for index, (name, path) in enumerate(versions):
        mark = ' (newest)' if index == len(versions) - 1 else ''
        locales = loader.load_version(path)
        files = ', '.join(f.name for f in loader.metadata_files(path))
        asset_count = sum(count for _c, _k, _d, count in assets.summary(path / 'assets'))
        print(f'{name:<10}{mark:<10} {len(locales):>3} locales, {asset_count:>3} assets   '
              f'[{files}]')
    return EXIT_OK


def cmd_diff(args):
    ws = _load(args)
    versions = loader.discover_versions(ws.versions_dir)
    if len(versions) < 2 and not (args.old and args.new):
        print('Two versions are necessary for a comparison.')
        return EXIT_OK
    new_name, new_path = loader.select_version(versions, args.new)
    if args.old:
        old_name, old_path = loader.select_version(versions, args.old)
    else:
        old_name, old_path = loader.previous_version(versions, new_name)
    if not old_path:
        print(f'{new_name} is the first version. There is nothing to compare.')
        return EXIT_OK

    ctx = rules.RuleContext(
        locales=loader.load_version(new_path), strategy=ws.strategy,
        groups=ws.config.groups(), primary_locale=ws.config.app.primary_locale,
        default_country=ws.config.app.default_country, version=new_name,
        prev_locales=loader.load_version(old_path), prev_version=old_name)
    found = rules.check_changelog(ctx)
    print(f'== {old_name} → {new_name} ==\n')
    if not found:
        print('The name, the subtitle, and the keyword fields are the same.')
        return EXIT_OK
    for line in found[0].detail.splitlines():
        print(f'  {line}')
    return EXIT_OK


def cmd_assets(args):
    ws = _load(args)
    versions = loader.discover_versions(ws.versions_dir)
    name, path = loader.select_version(versions, args.metadata_version)
    assets_dir = path / 'assets'
    rows = assets.summary(assets_dir)
    print(f'== Assets of metadata version {name} ==\n')
    if not rows:
        print(f'No asset in {assets_dir}.\n')
        print('The layout is:\n'
              '  assets/<locale>/screenshots/<device>/01-name.png\n'
              '  assets/<locale>/previews/<device>/01-name.mp4')
    else:
        print(f'  {"locale":<10} {"kind":<12} {"device":<14} files')
        for code, kind, device, count in rows:
            print(f'  {code:<10} {kind:<12} {device:<14} {count}')
    locales = loader.load_version(path)
    findings = assets.audit(assets_dir, locales, ws.config.assets,
                            ws.config.app.primary_locale)
    if findings:
        print('\n  Findings:')
        for item in findings:
            print(f'   [{item.severity}] {item.title}')
            if item.fix:
                print(f'            → {item.fix}')
    else:
        print('\n  No problem found.')
    return EXIT_OK


def cmd_rules(args):
    print('Audit rules. Switch one off with `audit.disable_rules` in aso.yaml.\n')
    for rule in rules.ALL_RULES + assets.ASSET_RULES:
        print(f'  {rule:<20} {rules.RULE_HELP.get(rule, "")}')
    print('\nThe full reference is in docs/rules.md.')
    return EXIT_OK


# -- live commands ------------------------------------------------------------

def cmd_rank(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    live.cmd_rank(ws, conn, countries=_split_list(args.countries) or None,
                  top=args.top, fresh=args.fresh)
    conn.close()
    return EXIT_OK


def cmd_competitors(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    live.cmd_competitors(ws, conn, country=args.country, fresh=args.fresh,
                         suggest=args.suggest)
    conn.close()
    return EXIT_OK


def cmd_discover(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    live.cmd_discover(ws, conn, country=args.country, deep=args.deep, fresh=args.fresh)
    conn.close()
    return EXIT_OK


def cmd_reviews(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    live.cmd_reviews(ws, conn, countries=_split_list(args.countries) or None,
                     pages=args.pages, fresh=args.fresh)
    conn.close()
    return EXIT_OK


def cmd_verify_groups(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    live.cmd_verify_groups(ws, conn, group=args.group, top=args.top, fresh=args.fresh)
    conn.close()
    return EXIT_OK


def cmd_lookup(args):
    identity = scaffold.fetch_identity(track_id=scaffold.parse_app_id(args.app),
                                       bundle_id=args.bundle_id or '',
                                       country=args.country)
    if not identity:
        print('No app found. Check the identifier, the bundle, or your network.',
              file=sys.stderr)
        return EXIT_ERROR
    for key in ('name', 'track_id', 'bundle_id', 'version', 'seller', 'url'):
        print(f'  {key:<10} {identity[key]}')
    return EXIT_OK


def cmd_cache(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    if args.clear:
        removed = db.cache_clear(conn)
        print(f'{removed} cached answer(s) removed.')
    else:
        row = conn.execute('SELECT COUNT(*) AS n FROM api_cache').fetchone()
        print(f'{row["n"]} cached answer(s) in {ws.db_path}.')
        print(f'The tool keeps each answer for {ws.config.cache_hours} hours. '
              'Use --clear to empty the cache.')
    conn.close()
    return EXIT_OK


def cmd_phrases(args):
    ws = _load(args)
    conn = db.connect(ws.db_path)
    candidates, seeds = phrases.generate(
        ws, conn, country=args.country, deep=args.deep, fresh=args.fresh,
        with_reviews=args.with_reviews, limit=args.limit,
        extra_roots=_split_list(args.roots))
    conn.close()
    phrases.print_report(candidates, seeds,
                         group_label=ws.config.app.default_country.upper())
    if args.write:
        added, _block = phrases.write_phrases(ws, candidates, minimum_score=args.min_score)
        if added:
            print(f'\nAdded {len(added)} phrase(s) to {ws.strategy_path}:')
            for phrase, score, _why in added:
                print(f'  - {phrase} (score {score})')
        else:
            print(f'\nNothing new to add at score {args.min_score} or above.')
    if args.write_seeds and seeds:
        added, _block = phrases.write_seeds(ws, seeds)
        if added:
            print(f'\nAdded {len(added)} seed keyword(s) to {ws.strategy_path}:')
            for term, score, _why in added:
                print(f'  - {term} (score {score})')
    if args.write or args.write_seeds:
        print('\nRead the file, correct the scores, then run `aso audit`.')
    return EXIT_OK


# -- App Store Connect --------------------------------------------------------

def cmd_auth(args):
    from .asc import client as asc_client

    ws = _load(args)
    try:
        creds = asc_client.Credentials.resolve(ws)
    except asc_client.ASCAuthError as exc:
        print(f'\n{exc}\n', file=sys.stderr)
        return EXIT_ERROR
    print('  key id      ' + creds.key_id)
    print('  issuer id   ' + creds.issuer_id)
    print('  key file    ' + (creds.key_path or 'from APP_STORE_CONNECT_PRIVATE_KEY'))
    print('  app id      ' + creds.app_id)
    if creds.key_path:
        try:
            inside = Path(creds.key_path).resolve().is_relative_to(ws.root.parent.resolve())
        except AttributeError:                      # Python 3.8 and older
            inside = str(ws.root.parent.resolve()) in str(Path(creds.key_path).resolve())
        if inside:
            print('\n  ⚠️  The key file is inside your project. Check that your '
                  '.gitignore holds *.p8.')
    if not args.check:
        print('\nThe credentials are complete. Add --check to call the API and confirm '
              'that Apple accepts them.')
        return EXIT_OK
    try:
        app = asc_client.ASCClient(creds, verbose=args.verbose).whoami()
    except (asc_client.ASCError, asc_client.ASCAuthError) as exc:
        print(f'\nApple refused the credentials:\n{exc}\n', file=sys.stderr)
        return EXIT_ERROR
    print(f'\n✅ Apple accepted the key. The app is "{app.get("name", "?")}" '
          f'({app.get("bundleId", "?")}).')
    return EXIT_OK


def cmd_pull(args):
    from .asc import pull

    ws = _load(args)
    return pull.cmd_pull(ws, version=args.metadata_version, from_editable=args.editable,
                         locale=args.locale, verbose=args.verbose)


def cmd_push(args):
    from .asc import push

    ws = _load(args)
    versions = loader.discover_versions(ws.versions_dir)
    name, path = loader.select_version(versions, args.metadata_version)
    print(f'Reading the metadata of version {name} from {path}')
    raw = loader.load_version_raw(path)
    if not raw:
        print(f'No locale in {path}.', file=sys.stderr)
        return EXIT_ERROR

    if not args.skip_audit:
        ctx, _path = _build_context(ws, name)
        findings = [s for s in rules.run_all(ctx, disabled=ws.config.disabled_rules)
                    if s.severity == 'CRITICAL']
        if findings:
            print('\nThe audit found problems that App Store Connect will refuse:',
                  file=sys.stderr)
            for item in findings:
                print(f'  🟥 {item.title}', file=sys.stderr)
            print('\nFix them, or use --skip-audit to push anyway.', file=sys.stderr)
            return EXIT_FINDINGS
    return push.cmd_push(ws, raw, dry_run=args.dry_run, only_locale=args.locale,
                         force=args.force, verbose=args.verbose)


def cmd_push_assets(args):
    from .asc import media

    ws = _load(args)
    versions = loader.discover_versions(ws.versions_dir)
    name, path = loader.select_version(versions, args.metadata_version)
    if not args.dir:
        print(f'Reading the assets of version {name} from {path / "assets"}')
    return media.cmd_push_assets(
        ws, assets_dir=path / 'assets', screenshots_dir=args.dir,
        videos_dir=args.videos_dir, only=args.only, locale=args.locale,
        device=args.device, all_locales=args.all_locales,
        missing_only=args.missing_only, dry_run=args.dry_run, force=args.force,
        verbose=args.verbose)


def cmd_where(args):
    ws = _load(args)
    print(f'  workspace  {ws.root}')
    print(f'  config     {ws.config_path}')
    print(f'  strategy   {ws.strategy_path}')
    print(f'  versions   {ws.versions_dir}')
    print(f'  reports    {ws.reports_dir}')
    print(f'  state      {ws.db_path}')
    print(f'  app        {ws.config.app.name or "(no name)"} '
          f'(track_id {ws.config.app.track_id or "not set"})')
    return EXIT_OK


# -- the parser ---------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog='aso',
        description='An App Store Optimization advisor for your versioned metadata.',
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version=f'aso-advisor {__version__}')
    parser.add_argument('--workspace', help='the workspace directory (default: search '
                                            'upwards for aso/)')
    sub = parser.add_subparsers(dest='command')

    p = sub.add_parser('init', help='make a new workspace')
    p.add_argument('--app-id', help='the numeric App Store identifier, or the page URL')
    p.add_argument('--bundle-id', help='the bundle identifier, for example com.example.app')
    p.add_argument('--path', help='where to write the workspace (default: ./aso)')
    p.add_argument('--locale', default='en-US', help='the primary locale (default en-US)')
    p.add_argument('--country', default='us', help='the home storefront (default us)')
    p.add_argument('--metadata-version', help='the name of the first version directory')
    p.add_argument('--force', action='store_true', help='overwrite the files that exist')
    p.set_defaults(func=cmd_init)

    p = sub.add_parser('audit', help='audit a metadata version and write a report')
    p.add_argument('--metadata-version', help='the version to audit (default: the newest)')
    p.add_argument('--json', action='store_true', help='write the result as JSON to stdout')
    p.add_argument('--no-report', action='store_true', help='do not write a report file')
    p.add_argument('--no-state', action='store_true',
                   help='do not write to the database (for a build pipeline)')
    p.add_argument('--no-assets', action='store_true', help='skip the asset checks')
    p.add_argument('--fail-on', choices=['critical', 'high', 'medium', 'low', 'info', 'none'],
                   default='none',
                   help='exit with code 2 if a suggestion is at this severity or above')
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser('list', help='list the suggestions')
    p.add_argument('--all', action='store_true', help='include dismissed and resolved items')
    p.add_argument('--severity', help='comma-separated filter, for example critical,high')
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('show', help='show one suggestion in full')
    p.add_argument('fid')
    p.set_defaults(func=cmd_show)

    p = sub.add_parser('dismiss', help='hide a suggestion in the next runs')
    p.add_argument('fid')
    p.add_argument('reason', nargs='?', default='')
    p.set_defaults(func=lambda a: _set_status(a, 'dismissed'))

    p = sub.add_parser('reopen', help='make a dismissed suggestion active again')
    p.add_argument('fid')
    p.set_defaults(func=lambda a: _set_status(a, 'open'))

    p = sub.add_parser('history', help='show the past runs')
    p.set_defaults(func=cmd_history)

    p = sub.add_parser('versions', help='list the metadata versions of the workspace')
    p.set_defaults(func=cmd_versions)

    p = sub.add_parser('diff', help='compare two metadata versions')
    p.add_argument('--old', help='the older version (default: the one before --new)')
    p.add_argument('--new', help='the newer version (default: the newest)')
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser('assets', help='audit the localized screenshots and previews')
    p.add_argument('--metadata-version')
    p.set_defaults(func=cmd_assets)

    p = sub.add_parser('rules', help='list the audit rules')
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser('rank', help='the live search position of your target phrases')
    p.add_argument('--countries', help='comma-separated country codes')
    p.add_argument('--top', type=int, default=100, help='results to read per term (max 200)')
    p.add_argument('--fresh', action='store_true', help='do not use the cache')
    p.set_defaults(func=cmd_rank)

    p = sub.add_parser('competitors', help='snapshot and compare the apps that you track')
    p.add_argument('--country')
    p.add_argument('--suggest', help='find candidate competitors for a search term')
    p.add_argument('--fresh', action='store_true')
    p.set_defaults(func=cmd_competitors)

    p = sub.add_parser('discover', help='keyword ideas from the App Store autocomplete')
    p.add_argument('--country')
    p.add_argument('--deep', action='store_true', help='expand the best suggestion one level')
    p.add_argument('--fresh', action='store_true')
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser('reviews', help='the words of your users and the rating pulse')
    p.add_argument('--countries')
    p.add_argument('--pages', type=int, default=3, help='RSS pages per storefront')
    p.add_argument('--fresh', action='store_true')
    p.set_defaults(func=cmd_reviews)

    p = sub.add_parser('verify-groups',
                       help='test the cross-localization table against the live store')
    p.add_argument('--group', help='storefront group, for example US')
    p.add_argument('--top', type=int, default=200)
    p.add_argument('--fresh', action='store_true')
    p.set_defaults(func=cmd_verify_groups)

    p = sub.add_parser('phrases', help='propose the target search phrases')
    p.add_argument('--country', help='the storefront to read (default: the home one)')
    p.add_argument('--roots', help='extra comma-separated root terms to expand')
    p.add_argument('--deep', action='store_true',
                   help='expand the best completion one more level')
    p.add_argument('--with-reviews', action='store_true',
                   help='also mine the words of your recent reviews')
    p.add_argument('--limit', type=int, default=25, help='how many rows to print')
    p.add_argument('--write', action='store_true',
                   help='add the strong proposals to phrase_targets in strategy.yaml')
    p.add_argument('--write-seeds', action='store_true',
                   help='add the one-word proposals to seed_keywords')
    p.add_argument('--min-score', type=int, default=6,
                   help='the lowest score that --write accepts (default 6)')
    p.add_argument('--fresh', action='store_true')
    p.set_defaults(func=cmd_phrases)

    p = sub.add_parser('auth', help='check the App Store Connect key, or learn to make one')
    p.add_argument('--check', action='store_true',
                   help='call the API and confirm that Apple accepts the key')
    p.add_argument('--verbose', action='store_true')
    p.set_defaults(func=cmd_auth)

    p = sub.add_parser('pull', help='read the live metadata into the workspace')
    p.add_argument('--metadata-version',
                   help='the version directory to write (default: the store version)')
    p.add_argument('--editable', action='store_true',
                   help='read the version that you prepare, not the live one')
    p.add_argument('--locale', help='read one locale only')
    p.add_argument('--verbose', action='store_true')
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser('push', help='send the metadata of a version to App Store Connect')
    p.add_argument('--metadata-version', help='the version to push (default: the newest)')
    p.add_argument('--dry-run', action='store_true',
                   help='print the intended changes and send nothing')
    p.add_argument('--locale', help='push one locale only')
    p.add_argument('--force', action='store_true',
                   help='allow a change to a version in WAITING_FOR_REVIEW')
    p.add_argument('--skip-audit', action='store_true',
                   help='push even when the audit finds a CRITICAL problem')
    p.add_argument('--verbose', action='store_true')
    p.set_defaults(func=cmd_push)

    p = sub.add_parser('push-assets',
                       help='upload the localized screenshots and preview videos')
    p.add_argument('--metadata-version', help='the version to read (default: the newest)')
    p.add_argument('--dir', help='read an external screenshot tree instead of the workspace')
    p.add_argument('--videos-dir', help='read the preview videos from another tree')
    p.add_argument('--only', choices=['screenshots', 'videos'], help='one family only')
    p.add_argument('--locale', help='one locale only')
    p.add_argument('--device', help='one device only, for example iphone-6.9 or ipad-13')
    p.add_argument('--all-locales', action='store_true',
                   help='a flat external tree applies to every localization of the version')
    p.add_argument('--missing-only', action='store_true',
                   help='upload only where the store has nothing yet')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true',
                   help='allow a change to a version in WAITING_FOR_REVIEW')
    p.add_argument('--verbose', action='store_true')
    p.set_defaults(func=cmd_push_assets)

    p = sub.add_parser('lookup', help='read the public data of an app')
    p.add_argument('app', nargs='?', help='the numeric identifier or the App Store URL')
    p.add_argument('--bundle-id')
    p.add_argument('--country', default='us')
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser('cache', help='show or empty the cache of the Apple answers')
    p.add_argument('--clear', action='store_true')
    p.set_defaults(func=cmd_cache)

    p = sub.add_parser('where', help='show the paths of the workspace')
    p.set_defaults(func=cmd_where)

    return parser


def main(argv=None):
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)
    if not getattr(args, 'command', None):
        # No subcommand means: audit the newest version.
        args = parser.parse_args([*argv, 'audit'])
    try:
        return args.func(args) or EXIT_OK
    except (WorkspaceError, loader.MetadataError) as exc:
        print(f'\n{exc}\n', file=sys.stderr)
        return EXIT_ERROR
    except SystemExit as exc:
        if exc.code not in (None, 0):
            print(f'\n{exc}\n', file=sys.stderr)
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    except BrokenPipeError:
        return EXIT_OK
    except KeyboardInterrupt:
        print('\nStopped.', file=sys.stderr)
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
