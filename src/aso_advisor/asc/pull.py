"""`aso pull`: read the live metadata from App Store Connect into the workspace.

The command writes one version directory. It keeps the `language:` notes and
the `*_eng` back-translations that the directory already has, and it replaces
every other value with what the store holds today.

Run it before an audit. The audit is only as correct as the YAML that it reads.
"""

from pathlib import Path

from .. import writer
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


def collect(client, from_editable=False, locale=None):
    """Return (version_name, {locale: {field: value}})."""
    if from_editable:
        version = find_editable_version(client, allow_waiting_for_review=True)
        app_info = find_editable_app_info(client)
        label = 'editable'
    else:
        version = find_live_version(client)
        app_info = find_live_app_info(client)
        label = 'live'

    version_id = version['id']
    attributes = version.get('attributes', {})
    version_name = attributes.get('versionString', 'unknown')
    print(f'{label} version: {version_name} '
          f'(state {attributes.get("appStoreState", "?")})')

    version_locales = list_version_localizations(client, version_id)
    info_locales = list_app_info_localizations(client, app_info['id'])

    codes = sorted(set(version_locales) | set(info_locales))
    if locale:
        if locale not in codes:
            available = ', '.join(codes)
            raise SystemExit(f'The app has no locale {locale!r}. It has: {available}')
        codes = [locale]

    out = {}
    for code in codes:
        fields = {}
        attrs = (version_locales.get(code) or {}).get('attributes', {})
        for asc_key, yaml_key in VERSION_ASC_TO_YAML.items():
            if attrs.get(asc_key) is not None:
                fields[yaml_key] = attrs[asc_key]
        attrs = (info_locales.get(code) or {}).get('attributes', {})
        for asc_key, yaml_key in APP_INFO_ASC_TO_YAML.items():
            if attrs.get(asc_key) is not None:
                fields[yaml_key] = attrs[asc_key]
        out[code] = fields
    return version_name, out


def cmd_pull(ws, version=None, from_editable=False, locale=None, verbose=False,
             client=None):
    """Write the metadata of the store into `aso/versions/<version>/`."""
    client = client or ASCClient(Credentials.resolve(ws), verbose=verbose)
    version_name, locales = collect(client, from_editable=from_editable, locale=locale)
    if not locales:
        print('The store returned no localization.')
        return 0

    target = Path(version or version_name)
    if not target.is_absolute() and len(target.parts) == 1:
        target = ws.versions_dir / target.name

    existed = target.is_dir()
    written = writer.write_version(target, locales, preserve_from=target if existed else None)

    print(f'\n{len(locales)} locale(s) written into {target}:')
    for path in written:
        print(f'  {path}')
    if not existed:
        print('\nThis is a new version directory. Run `aso audit` to see what the '
              'store holds today.')
    else:
        print('\nRun `aso diff` to see what changed, then `aso audit`.')
    return 0
