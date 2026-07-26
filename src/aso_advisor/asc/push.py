"""`aso push`: send the metadata of a version directory to App Store Connect.

The command works locale by locale. One bad locale does not stop the others,
and the exit code is not zero when any locale failed.

Four things happen before the first change:

- Field lengths are checked on your machine. A field that is too long stops
  the push, and the message names the locale and the field.
- The audit runs, and a CRITICAL finding stops the push. Use `--skip-audit` if
  you disagree.
- The tool reads the values that the store holds now, and prints the exact
  difference. A locale with no difference is skipped, so a repeated push sends
  nothing.
- The values of the store go into a backup directory, so you can put them back
  if a push was wrong.
"""

import sys
import time
from pathlib import Path

from .. import compare, db, writer
from ..color import paint
from .client import (
    APP_INFO_ASC_TO_YAML,
    APP_INFO_LOCALIZATION_FIELDS,
    VERSION_ASC_TO_YAML,
    VERSION_LOCALIZATION_FIELDS,
    ASCClient,
    ASCError,
    Credentials,
    find_editable_app_info,
    find_editable_version,
    list_app_info_localizations,
    list_version_localizations,
    project_yaml,
    select_locales,
    validate_locale_fields,
)

PUSHABLE_FIELDS = set(VERSION_LOCALIZATION_FIELDS) | set(APP_INFO_LOCALIZATION_FIELDS)


def remote_view(version_locales, info_locales):
    """The current values of the store, in the shape of the YAML files."""
    out = {}
    for source, mapping in ((version_locales, VERSION_ASC_TO_YAML),
                            (info_locales, APP_INFO_ASC_TO_YAML)):
        for code, item in source.items():
            attributes = item.get('attributes', {})
            fields = out.setdefault(code, {})
            for asc_key, yaml_key in mapping.items():
                if attributes.get(asc_key) is not None:
                    fields[yaml_key] = attributes[asc_key]
    return out


def _is_duplicate_locale(error):
    return error.status == 409 and any(
        'DUPLICATE' in str(item.get('code', '')) for item in error.errors)


def _upsert(client, kind, parent_type, parent_id, locale, existing, fields, mapping,
            dry_run):
    """Create or update one localization. Returns a line for the log."""
    attributes = project_yaml(fields, mapping)
    if not attributes:
        return f'no {kind} field'

    def patch(localization_id, note=''):
        if dry_run:
            return f'would update {localization_id} ({", ".join(sorted(attributes))})'
        client.request('PATCH', f'/v1/{kind}s/{localization_id}', json_body={
            'data': {'type': f'{kind}s', 'id': localization_id, 'attributes': attributes}})
        return f'updated {localization_id}'

    if locale in existing:
        return patch(existing[locale]['id'])

    if dry_run:
        return f'would create for {locale} ({", ".join(sorted(attributes))})'
    body = {'data': {
        'type': f'{kind}s',
        'attributes': {**attributes, 'locale': locale},
        'relationships': {parent_type: {'data': {'type': f'{parent_type}s',
                                                 'id': parent_id}}},
    }}
    try:
        client.request('POST', f'/v1/{kind}s', json_body=body)
        return f'created for {locale}'
    except ASCError as exc:
        # App Store Connect sometimes makes the localization itself. Update it.
        if _is_duplicate_locale(exc):
            refreshed = (list_version_localizations(client, parent_id)
                         if kind == 'appStoreVersionLocalization'
                         else list_app_info_localizations(client, parent_id))
            if locale in refreshed:
                existing[locale] = refreshed[locale]
                return patch(refreshed[locale]['id'], note=' (it existed; updated instead)')
        raise


def write_backup(ws, version_name, remote):
    """Keep the values of the store before a push. Returns the directory."""
    if not remote:
        return None
    target = Path(ws.state_dir) / 'backups' / f'{int(time.time())}-before-push'
    writer.write_version(target, remote)
    (target / 'README.txt').write_text(
        f'The values that App Store Connect held for version {version_name} before a '
        'push.\nTo put them back, copy the YAML files into a version directory and run '
        '`aso push`.\n', encoding='utf-8')
    return target


def cmd_push(ws, locales, dry_run=False, only_locale=None, force=False, verbose=False,
             version_name='', backup=True, client=None):
    """Push `{locale: {field: value}}`. Returns an exit code."""
    errors = []
    for code, fields in select_locales(locales, only_locale):
        errors.extend(validate_locale_fields(code, fields))
    if errors:
        print('The metadata does not pass the length check:', file=sys.stderr)
        for line in errors:
            print(f'  - {line}', file=sys.stderr)
        return 2

    client = client or ASCClient(Credentials.resolve(ws), verbose=verbose)
    version = find_editable_version(client, allow_waiting_for_review=force)
    version_id = version['id']
    attributes = version.get('attributes', {})
    version_name = version_name or attributes.get('versionString', '?')
    print(f'Editable version: {attributes.get("versionString", "?")} '
          f'(state {attributes.get("appStoreState", "?")})')

    app_info = find_editable_app_info(client)
    app_info_id = app_info['id']
    existing_version = list_version_localizations(client, version_id)
    existing_info = list_app_info_localizations(client, app_info_id)

    wanted = dict(select_locales(locales, only_locale))
    current = remote_view(existing_version, existing_info)
    current = {code: fields for code, fields in current.items() if code in wanted}
    changes = compare.diff_locales(wanted, current, fields=PUSHABLE_FIELDS)
    changed_locales = {change.locale for change in changes}

    if not changes:
        print('\n✅ Every locale already holds these values. There is nothing to send.')
        return 0

    locale_count, field_count = compare.summarize(changes)
    print(f'\n{field_count} field(s) in {locale_count} locale(s) would change:\n')
    for line in compare.format_changes(changes, 'new', 'store', paint=paint):
        print(line)

    if dry_run:
        print('\n(dry run — the tool sent nothing)')
        return 0

    backup_dir = write_backup(ws, version_name, current) if backup else None
    if backup_dir:
        print(f'\nThe values of the store are in {backup_dir}')

    done, failed, skipped = [], [], []
    for code, fields in select_locales(locales, only_locale):
        if code not in changed_locales:
            skipped.append(code)
            continue
        print(f'\n[{code}]')
        try:
            message = _upsert(client, 'appStoreVersionLocalization', 'appStoreVersion',
                              version_id, code, existing_version, fields,
                              VERSION_LOCALIZATION_FIELDS, dry_run)
            print(f'  version: {message}')
            message = _upsert(client, 'appInfoLocalization', 'appInfo', app_info_id,
                              code, existing_info, fields, APP_INFO_LOCALIZATION_FIELDS,
                              dry_run)
            print(f'  app info: {message}')
            done.append(code)
        except ASCError as exc:
            print(f'  FAILED: {exc}', file=sys.stderr)
            failed.append((code, str(exc)))
        except Exception as exc:                    # noqa: BLE001 - one locale must not stop the rest
            print(f'  FAILED ({type(exc).__name__}): {exc}', file=sys.stderr)
            failed.append((code, f'{type(exc).__name__}: {exc}'))

    print('\n' + '=' * 60)
    print(f'Done. Sent: {len(done)}   Already correct: {len(skipped)}   '
          f'Failed: {len(failed)}')
    if failed:
        print('\nFailures:')
        for code, message in failed:
            print(f'  - {code}: {message.splitlines()[0]}')
        return 1

    if done:
        conn = db.connect(ws.db_path)
        try:
            db.save_sync_snapshot(conn, version_name, wanted, 'push')
        finally:
            conn.close()
    print('\nApple shows the new text on the product page after review. '
          'Run `aso pull --check` later to confirm what is live.')
    return 0
