"""`aso push`: send the metadata of a version directory to App Store Connect.

The command works locale by locale. One bad locale does not stop the others,
and the exit code is not zero when any locale failed.

Two guards run before the first request:

- Field lengths are checked on your machine. A field that is too long stops
  the push, and the message names the locale and the field.
- The audit runs, and a CRITICAL finding stops the push. Use `--skip-audit` if
  you disagree.
"""

import sys

from .client import (
    APP_INFO_LOCALIZATION_FIELDS,
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


def _is_duplicate_locale(error):
    return error.status == 409 and any(
        'DUPLICATE' in str(item.get('code', '')) for item in error.errors)


def _upsert(client, kind, parent_type, parent_id, locale, existing, fields, mapping,
            dry_run):
    """Create or update one localization. Returns a line for the log."""
    attributes = project_yaml(fields, mapping)
    if not attributes:
        return f'skipped (no {kind} field)'

    def patch(localization_id, note=''):
        if dry_run:
            return f'would update {kind} {localization_id} ({", ".join(sorted(attributes))})'
        client.request('PATCH', f'/v1/{kind}s/{localization_id}', json_body={
            'data': {'type': f'{kind}s', 'id': localization_id, 'attributes': attributes}})
        return f'updated {kind} {localization_id}{note}'

    if locale in existing:
        return patch(existing[locale]['id'])

    if dry_run:
        return f'would create {kind} for {locale} ({", ".join(sorted(attributes))})'
    body = {'data': {
        'type': f'{kind}s',
        'attributes': {**attributes, 'locale': locale},
        'relationships': {parent_type: {'data': {'type': f'{parent_type}s',
                                                 'id': parent_id}}},
    }}
    try:
        client.request('POST', f'/v1/{kind}s', json_body=body)
        return f'created {kind} for {locale}'
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


def cmd_push(ws, locales, dry_run=False, only_locale=None, force=False, verbose=False,
             client=None):
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
    print(f'Editable version: {attributes.get("versionString", "?")} '
          f'(state {attributes.get("appStoreState", "?")})')

    app_info = find_editable_app_info(client)
    app_info_id = app_info['id']

    existing_version = list_version_localizations(client, version_id)
    existing_info = list_app_info_localizations(client, app_info_id)
    if dry_run:
        print('(dry run — the tool sends nothing)')

    done, failed = [], []
    for code, fields in select_locales(locales, only_locale):
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
    print(f'Done. Success: {len(done)}   Failed: {len(failed)}')
    if failed:
        print('\nFailures:')
        for code, message in failed:
            print(f'  - {code}: {message.splitlines()[0]}')
        return 1
    if not dry_run:
        print('\nApple shows the new text on the product page after review. '
              'Run `aso pull` later to confirm what is live.')
    return 0
