"""`aso push-assets`: sync screenshots and app preview videos.

The command uploads only what changed. App Store Connect keeps an MD5 checksum
per asset. When the checksums of a set are the same as the checksums of your
files, in the same order, the tool skips the set.

Two source layouts work.

The workspace layout, which `aso audit` also reads:

    versions/2.1/assets/en-US/screenshots/iphone-6.9/01-hero.png
    versions/2.1/assets/en-US/previews/iphone-6.9/01-demo.mp4

An external tree, with `--dir` and `--videos-dir`. Directory names are read
loosely, so a folder from a design tool works without a rename:

    English (en-US)/iOS Phones  6.9/01.png     locale first
    en-US/phone/01.png                          locale first, short names
    phone/01.png                                flat, needs --locale
    iPhone/en-US/app_preview.mp4                device first, videos

The file name order is the display order on the store. Use a numeric prefix.
"""

import hashlib
import re
import sys
from pathlib import Path

from .client import (
    ASCClient,
    ASCError,
    Credentials,
    find_editable_version,
    list_version_localizations,
)

# App Store Connect has no 6.9-inch screenshot type. A 6.9-inch image uploads
# as the 6.7-inch type, and the store shows it on the large devices.
DEVICE_DISPLAY_TYPES = {
    'phone': 'APP_IPHONE_67',
    'iphone69': 'APP_IPHONE_67',
    'iphone67': 'APP_IPHONE_67',
    'iphone65': 'APP_IPHONE_65',
    'iphone63': 'APP_IPHONE_61',
    'iphone61': 'APP_IPHONE_61',
    'iphone58': 'APP_IPHONE_58',
    'iphone55': 'APP_IPHONE_55',
    'iphone47': 'APP_IPHONE_47',
    'ipad': 'APP_IPAD_PRO_3GEN_129',
    'ipad13': 'APP_IPAD_PRO_3GEN_129',
    'ipad129': 'APP_IPAD_PRO_3GEN_129',
    'ipad11': 'APP_IPAD_PRO_3GEN_11',
    'ipad105': 'APP_IPAD_105',
    'ipad97': 'APP_IPAD_97',
}

# Sizes in inches, as they appear in directory names such as "iOS Phones  6.9".
PHONE_SIZE_TYPES = {
    '6.9': 'APP_IPHONE_67', '6.7': 'APP_IPHONE_67', '6.5': 'APP_IPHONE_65',
    '6.3': 'APP_IPHONE_61', '6.1': 'APP_IPHONE_61', '5.8': 'APP_IPHONE_58',
    '5.5': 'APP_IPHONE_55', '4.7': 'APP_IPHONE_47',
}
IPAD_SIZE_TYPES = {
    '13': 'APP_IPAD_PRO_3GEN_129', '12.9': 'APP_IPAD_PRO_3GEN_129',
    '11': 'APP_IPAD_PRO_3GEN_11', '10.5': 'APP_IPAD_105', '9.7': 'APP_IPAD_97',
}

# App previews use their own list of types, also without a 6.9-inch entry.
DISPLAY_TO_PREVIEW_TYPE = {
    'APP_IPHONE_69': 'IPHONE_67',
    'APP_IPHONE_67': 'IPHONE_67',
    'APP_IPHONE_65': 'IPHONE_65',
    'APP_IPHONE_61': 'IPHONE_61',
    'APP_IPHONE_58': 'IPHONE_58',
    'APP_IPHONE_55': 'IPHONE_55',
    'APP_IPHONE_47': 'IPHONE_47',
    'APP_IPAD_PRO_3GEN_129': 'IPAD_PRO_3GEN_129',
    'APP_IPAD_PRO_3GEN_11': 'IPAD_PRO_3GEN_11',
    'APP_IPAD_105': 'IPAD_105',
    'APP_IPAD_97': 'IPAD_97',
}

MAX_PREVIEWS_PER_SET = 3
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg')
VIDEO_SUFFIXES = ('.mp4', '.mov', '.m4v')

LOCALE_IN_PARENTHESES = re.compile(r'\(([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)?)\)\s*$')
BARE_LOCALE = re.compile(r'^[a-z]{2,3}(-[A-Za-z0-9]+)?$')

# The two asset families use the same flow, with different endpoint names.
SCREENSHOT_SPEC = {
    'kind': 'screenshot',
    'asset_type': 'appScreenshots',
    'set_type': 'appScreenshotSets',
    'set_relationship': 'appScreenshotSet',
    'display_attr': 'screenshotDisplayType',
}
PREVIEW_SPEC = {
    'kind': 'preview',
    'asset_type': 'appPreviews',
    'set_type': 'appPreviewSets',
    'set_relationship': 'appPreviewSet',
    'display_attr': 'previewType',
}


# -- names --------------------------------------------------------------------

def classify_device_dir(name):
    """A directory name to a screenshot display type, or None."""
    compact = re.sub(r'[\s_.\'"-]+', '', str(name).lower())
    if compact in DEVICE_DISPLAY_TYPES:
        return DEVICE_DISPLAY_TYPES[compact]
    if compact.startswith('app') and compact.upper().replace('APP', 'APP_'):
        raw = str(name).strip().upper()
        if raw in DISPLAY_TO_PREVIEW_TYPE:
            return raw
    low = str(name).lower()
    size = re.search(r'(\d+(?:\.\d+)?)', low)
    size = size.group(1) if size else None
    if 'ipad' in low or 'tablet' in low:
        return IPAD_SIZE_TYPES.get(size, 'APP_IPAD_PRO_3GEN_129')
    if 'phone' in low:
        return PHONE_SIZE_TYPES.get(size, 'APP_IPHONE_67')
    return None


def classify_preview_dir(name):
    """A directory name to an app preview type, or None."""
    raw = str(name).strip().upper()
    if raw in DISPLAY_TO_PREVIEW_TYPE.values():
        return raw
    display = classify_device_dir(name)
    return DISPLAY_TO_PREVIEW_TYPE.get(display) if display else None


def locale_of_dir(name):
    """The locale code of 'English (en-US)' or of a bare 'en-US', or None."""
    match = LOCALE_IN_PARENTHESES.search(str(name))
    if match:
        code = match.group(1)
        parts = code.split('-', 1)
        return parts[0].lower() + ('-' + parts[1] if len(parts) > 1 else '')
    name = str(name)
    if BARE_LOCALE.match(name) or re.match(r'^[a-z]{2}-[A-Z][a-z]+$', name):
        return name
    return None


def files_in(directory, suffixes=IMAGE_SUFFIXES):
    return sorted(p for p in Path(directory).iterdir()
                  if p.is_file() and p.suffix.lower() in suffixes)


def md5_of(path):
    digest = hashlib.md5()                          # noqa: S324 - Apple asks for MD5
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


# -- what to upload -----------------------------------------------------------

def plan_from_workspace(assets_dir, kind='screenshots', locale=None, device=None):
    """{locale: {asc_type: [files]}} from the assets tree of a version."""
    assets_dir = Path(assets_dir)
    suffixes = IMAGE_SUFFIXES if kind == 'screenshots' else VIDEO_SUFFIXES
    classify = classify_device_dir if kind == 'screenshots' else classify_preview_dir
    wanted_type = _device_filter(device, kind)
    plan = {}
    if not assets_dir.is_dir():
        return plan
    for locale_dir in sorted(p for p in assets_dir.iterdir() if p.is_dir()):
        code = locale_dir.name
        if locale and code != locale:
            continue
        kind_dir = locale_dir / kind
        if not kind_dir.is_dir():
            continue
        for device_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            asc_type = classify(device_dir.name)
            if asc_type is None:
                print(f'  (skip {code}/{device_dir.name}: the device name is not known)')
                continue
            if wanted_type and asc_type != wanted_type:
                continue
            files = files_in(device_dir, suffixes)
            if files:
                plan.setdefault(code, {})[asc_type] = files
    return plan


def _device_filter(device, kind):
    if not device:
        return None
    if kind == 'screenshots':
        return classify_device_dir(device) or str(device).upper()
    return classify_preview_dir(device) or str(device).upper()


def plan_from_tree(root, kind='screenshots', locale=None, device=None,
                   all_locales=False, known_locales=()):
    """{locale: {asc_type: [files]}} from an external tree of assets."""
    root = Path(root).expanduser()
    if not root.is_dir():
        raise SystemExit(f'This directory does not exist: {root}')
    suffixes = IMAGE_SUFFIXES if kind == 'screenshots' else VIDEO_SUFFIXES
    classify = classify_device_dir if kind == 'screenshots' else classify_preview_dir
    wanted_type = _device_filter(device, kind)
    plan = {}

    def add(code, asc_type, files):
        if not files or (wanted_type and asc_type != wanted_type):
            return
        if locale and code != locale:
            return
        plan.setdefault(code, {})[asc_type] = files

    skipped = []
    for top in sorted(p for p in root.iterdir() if p.is_dir()):
        asc_type = classify(top.name)
        if asc_type:
            # Device first: locale directories below the device directory.
            for child in sorted(p for p in top.iterdir() if p.is_dir()):
                code = locale_of_dir(child.name)
                if code:
                    add(code, asc_type, files_in(child, suffixes))
            # Flat: the files sit directly in the device directory.
            direct = files_in(top, suffixes)
            if direct:
                targets = list(known_locales) if all_locales else [locale or 'en-US']
                for code in targets:
                    add(code, asc_type, direct)
            continue
        code = locale_of_dir(top.name)
        if not code:
            skipped.append(top.name)
            continue
        for device_dir in sorted(p for p in top.iterdir() if p.is_dir()):
            inner = classify(device_dir.name)
            if inner:
                add(code, inner, files_in(device_dir, suffixes))
        # A locale directory can also hold `screenshots/` or `previews/`.
        nested = top / kind
        if nested.is_dir():
            for device_dir in sorted(p for p in nested.iterdir() if p.is_dir()):
                inner = classify(device_dir.name)
                if inner:
                    add(code, inner, files_in(device_dir, suffixes))
    if skipped:
        print(f'  (skipping the directories that are not locales: {", ".join(skipped)})')
    return plan


# -- the App Store Connect side -----------------------------------------------

def get_sets(client, spec, localization_id):
    items = client.get_all(
        f'/v1/appStoreVersionLocalizations/{localization_id}/{spec["set_type"]}')
    return {item['attributes'][spec['display_attr']]: item for item in items}


def get_assets(client, spec, set_id):
    return client.get_all(f'/v1/{spec["set_type"]}/{set_id}/{spec["asset_type"]}')


def create_set(client, spec, localization_id, asc_type):
    payload = client.request('POST', f'/v1/{spec["set_type"]}', json_body={'data': {
        'type': spec['set_type'],
        'attributes': {spec['display_attr']: asc_type},
        'relationships': {'appStoreVersionLocalization': {
            'data': {'type': 'appStoreVersionLocalizations', 'id': localization_id}}},
    }})
    return payload['data']['id']


def delete_asset(client, spec, asset_id):
    client.request('DELETE', f'/v1/{spec["asset_type"]}/{asset_id}')


def upload_asset(client, spec, set_id, path):
    """Reserve, send the chunks, then commit the checksum."""
    data = Path(path).read_bytes()
    reservation = client.request('POST', f'/v1/{spec["asset_type"]}', json_body={'data': {
        'type': spec['asset_type'],
        'attributes': {'fileName': Path(path).name, 'fileSize': len(data)},
        'relationships': {spec['set_relationship']: {
            'data': {'type': spec['set_type'], 'id': set_id}}},
    }})
    asset = reservation['data']
    operations = asset['attributes'].get('uploadOperations') or []
    if not operations:
        raise ASCError(0, [], f'{Path(path).name}: the store returned no upload operation.')
    for operation in operations:
        client.upload_chunk(operation, data)
    client.request('PATCH', f'/v1/{spec["asset_type"]}/{asset["id"]}', json_body={'data': {
        'type': spec['asset_type'],
        'id': asset['id'],
        'attributes': {'uploaded': True, 'sourceFileChecksum': md5_of(path)},
    }})
    return asset['id']


def sync_sets(client, spec, localization_id, wanted, locale, dry_run=False,
              missing_only=False, failures=None):
    """Compare and upload one locale for one asset family."""
    failures = failures if failures is not None else []
    changed = unchanged = 0
    sets = get_sets(client, spec, localization_id)

    for asc_type, files in sorted(wanted.items()):
        label = f'{locale}/{asc_type}'
        try:
            if spec is PREVIEW_SPEC and len(files) > MAX_PREVIEWS_PER_SET:
                raise ASCError(0, [], f'{label}: {len(files)} videos. The store takes at '
                                      f'most {MAX_PREVIEWS_PER_SET} previews per set.')
            existing = sets.get(asc_type)
            remote = get_assets(client, spec, existing['id']) if existing else []
            remote_checksums = [item['attributes'].get('sourceFileChecksum') or ''
                                for item in remote]
            local_checksums = [md5_of(f) for f in files]

            if remote_checksums == local_checksums:
                print(f'[{label}] up to date ({len(files)} {spec["kind"]}(s))')
                unchanged += 1
                continue
            if missing_only and remote:
                print(f'[{label}] skipped: the store already holds {len(remote)} '
                      f'{spec["kind"]}(s) (--missing-only)')
                unchanged += 1
                continue

            action = 'would replace' if dry_run else 'replacing'
            print(f'[{label}] store={len(remote)} local={len(files)} -> {action}')
            changed += 1
            if dry_run:
                continue

            for item in remote:
                delete_asset(client, spec, item['id'])
            set_id = existing['id'] if existing else create_set(
                client, spec, localization_id, asc_type)
            for file in files:
                upload_asset(client, spec, set_id, file)
                print(f'    uploaded {file.name}')

            bad = [f'{item["attributes"].get("fileName")} '
                   f'({(item["attributes"].get("assetDeliveryState") or {}).get("state")})'
                   for item in get_assets(client, spec, set_id)
                   if (item['attributes'].get('assetDeliveryState') or {}).get('state')
                   == 'FAILED']
            if bad:
                raise ASCError(0, [], f'{label}: the store refused {", ".join(bad)}')
        except ASCError as exc:
            print(f'[{label}] FAILED: {exc}', file=sys.stderr)
            failures.append((label, str(exc)))
    return changed, unchanged


def cmd_push_assets(ws, assets_dir=None, screenshots_dir=None, videos_dir=None,
                    only=None, locale=None, device=None, all_locales=False,
                    missing_only=False, dry_run=False, force=False, verbose=False,
                    client=None):
    """Upload the screenshots and the app previews of one version."""
    client = client or ASCClient(Credentials.resolve(ws), verbose=verbose)
    version = find_editable_version(client, allow_waiting_for_review=force)
    attributes = version.get('attributes', {})
    print(f'Editable version: {attributes.get("versionString", "?")} '
          f'(state {attributes.get("appStoreState", "?")})')
    localizations = list_version_localizations(client, version['id'])
    known = sorted(localizations)

    plans = []
    if only != 'videos':
        if screenshots_dir:
            plan = plan_from_tree(screenshots_dir, 'screenshots', locale, device,
                                  all_locales, known)
        else:
            plan = plan_from_workspace(assets_dir, 'screenshots', locale, device)
        if plan:
            plans.append((SCREENSHOT_SPEC, plan))
    if only != 'screenshots':
        if videos_dir:
            plan = plan_from_tree(videos_dir, 'previews', locale, device, all_locales, known)
        elif screenshots_dir:
            plan = plan_from_tree(screenshots_dir, 'previews', locale, device,
                                  all_locales, known)
        else:
            plan = plan_from_workspace(assets_dir, 'previews', locale, device)
        if plan:
            plans.append((PREVIEW_SPEC, plan))

    if not plans:
        source = screenshots_dir or videos_dir or assets_dir
        print(f'\nNo asset found under {source}.\n'
              'The workspace layout is:\n'
              '  assets/<locale>/screenshots/<device>/01-name.png\n'
              '  assets/<locale>/previews/<device>/01-name.mp4\n'
              'Use --dir to read a tree that lives somewhere else.')
        return 1
    if dry_run:
        print('(dry run — the tool uploads and deletes nothing)')

    changed = unchanged = 0
    failures = []
    for spec, plan in plans:
        total = sum(len(files) for sets in plan.values() for files in sets.values())
        print(f'\n== {spec["kind"]}s: {total} file(s) in {len(plan)} locale(s) ==')
        for code in sorted(plan):
            if code not in localizations:
                print(f'[{code}] SKIPPED: the version has no localization for it. '
                      'Run `aso push` for this locale first.')
                failures.append((code, 'the localization does not exist'))
                continue
            one, two = sync_sets(client, spec, localizations[code]['id'], plan[code],
                                 code, dry_run=dry_run, missing_only=missing_only,
                                 failures=failures)
            changed += one
            unchanged += two

    print('\n' + '=' * 60)
    print(f'Changed: {changed}   Up to date: {unchanged}   Failed: {len(failures)}')
    if failures:
        for label, message in failures:
            print(f'  - {label}: {message.splitlines()[0]}', file=sys.stderr)
        return 1
    if changed and not dry_run:
        print('Apple processes the uploads in the background. Screenshots appear after '
              'some minutes. A preview video takes longer, because the store makes its '
              'own copies.')
    return 0
