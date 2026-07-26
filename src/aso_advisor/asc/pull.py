"""`aso pull`: read the live metadata from App Store Connect into the workspace.

The command writes one version directory. It keeps the `language:` notes and
the `*_eng` back-translations that the directory already has, and it replaces
every other value with what the store holds today.

Two safety rules:

- `--check` writes nothing. It reports the differences and returns exit code 2
  when the workspace and the store do not match. Use it in a weekly job to
  find the changes that somebody made in the web interface.
- A plain `aso pull` refuses to overwrite work that you did not push. The tool
  remembers the values of the last pull and the last push, so it can tell a
  local draft from a change that came from the store.
"""

from pathlib import Path

from .. import compare, db, loader, writer
from ..color import paint
from .client import (
    APP_INFO_ASC_TO_YAML,
    VERSION_ASC_TO_YAML,
    ASCClient,
    Credentials,
    find_editable_app_info,
    find_editable_version,
    find_live_app_info,
    find_live_version,
    list_app_info_localizations,
    list_version_localizations,
)

EXIT_OK = 0
EXIT_DRIFT = 2


def collect(client, from_editable=False, locale=None, quiet=False):
    """Return (version_name, {locale: {field: value}})."""
    if from_editable:
        version = find_editable_version(client, allow_waiting_for_review=True)
        app_info = find_editable_app_info(client)
        label = 'editable'
    else:
        version = find_live_version(client)
        app_info = find_live_app_info(client)
        label = 'live'

    attributes = version.get('attributes', {})
    version_name = attributes.get('versionString', 'unknown')
    if not quiet:
        print(f'{label} version: {version_name} '
              f'(state {attributes.get("appStoreState", "?")})')

    version_locales = list_version_localizations(client, version['id'])
    info_locales = list_app_info_localizations(client, app_info['id'])

    codes = sorted(set(version_locales) | set(info_locales))
    if locale:
        if locale not in codes:
            raise SystemExit(f'The app has no locale {locale!r}. It has: '
                             + ', '.join(codes))
        codes = [locale]

    out = {}
    for code in codes:
        fields = {}
        for source, mapping in ((version_locales, VERSION_ASC_TO_YAML),
                                (info_locales, APP_INFO_ASC_TO_YAML)):
            attrs = (source.get(code) or {}).get('attributes', {})
            for asc_key, yaml_key in mapping.items():
                if attrs.get(asc_key) is not None:
                    fields[yaml_key] = attrs[asc_key]
        out[code] = fields
    return version_name, out


def local_metadata(path):
    """The metadata of a version directory, or {} when it has none."""
    try:
        return loader.load_version_raw(path)
    except loader.MetadataError:
        return {}


def cmd_pull(ws, version=None, from_editable=False, locale=None, verbose=False,
             check=False, force=False, client=None):
    """Read the store into the workspace, or compare the two with `check`."""
    client = client or ASCClient(Credentials.resolve(ws), verbose=verbose)
    version_name, remote = collect(client, from_editable=from_editable, locale=locale)
    if not remote:
        print('The store returned no localization.')
        return EXIT_OK

    target = Path(version or version_name)
    if not target.is_absolute() and len(target.parts) == 1:
        target = ws.versions_dir / target.name

    existed = target.is_dir()
    local = local_metadata(target) if existed else {}
    if locale:
        local = {code: fields for code, fields in local.items() if code == locale}
    changes = compare.diff_locales(local, remote)

    if check:
        return _report_check(target, changes)

    if changes and existed and not force:
        blocked = _unpushed(ws, target.name, local, changes)
        if blocked:
            return _refuse(target, blocked, changes)

    written = writer.write_version(target, remote,
                                   preserve_from=target if existed else None)
    _remember(ws, target.name, remote, 'pull')

    print(f'\n{len(remote)} locale(s) written into {target}:')
    for path in written:
        print(f'  {path}')
    if changes:
        locales, fields = compare.summarize(changes)
        print(f'\n{fields} field(s) in {locales} locale(s) changed:')
        for line in compare.format_changes(changes, 'yours', 'store', paint=paint):
            print(f'  {line}')
    print('\nRun `aso audit` to see what the store holds today.'
          if not existed else '\nRun `aso diff` and `aso audit`.')
    return EXIT_OK


def _report_check(target, changes):
    if not changes:
        print(f'\n✅ {target} matches the store.')
        return EXIT_OK
    locales, fields = compare.summarize(changes)
    print(f'\n⚠️  {fields} field(s) in {locales} locale(s) differ from the store.\n')
    for line in compare.format_changes(changes, 'yours', 'store', paint=paint):
        print(line)
    print('\n"yours" is the workspace, "store" is App Store Connect.\n'
          'Run `aso pull` to take the values of the store, or `aso push` to send '
          'yours.')
    return EXIT_DRIFT


def _unpushed(ws, version_name, local, changes):
    """The changes that only exist in the workspace, and that a pull would lose.

    The tool stores the values of the last pull and the last push. A field that
    is not the same as that record is work that nobody sent to the store yet.
    """
    conn = db.connect(ws.db_path)
    try:
        remembered, _stamp, _source = db.load_sync_snapshot(conn, version_name)
    finally:
        conn.close()
    if not remembered:
        # No record. Be careful and treat every difference as unpushed work.
        return [c for c in changes if c.kind in (compare.CHANGED, compare.ONLY_LEFT)]
    out = []
    for change in changes:
        if change.kind == compare.ONLY_RIGHT:
            continue
        known = (remembered.get(change.locale) or {}).get(change.field, '')
        if str(known) != str(change.left):
            out.append(change)
    return out


def _refuse(target, blocked, changes):
    locales, fields = compare.summarize(blocked)
    print(f'\n⛔ {target} holds {fields} field(s) in {locales} locale(s) that the '
          'store does not have.\n')
    for line in compare.format_changes(blocked, 'yours', 'store', paint=paint):
        print(line)
    print('\nA pull would replace them. Choose one:\n'
          '  aso pull --force                     take the store and lose the work above\n'
          '  aso pull --metadata-version <name>   write the store into another directory\n'
          '  aso push --dry-run                   send your work to the store instead\n'
          '  aso pull --check                     only report, never write')
    if len(changes) > len(blocked):
        print(f'\n({len(changes) - len(blocked)} other field(s) changed on the store '
              'side only.)')
    return EXIT_DRIFT


def _remember(ws, version_name, locales, source):
    conn = db.connect(ws.db_path)
    try:
        db.save_sync_snapshot(conn, version_name, locales, source)
    finally:
        conn.close()
