"""Audit of the localized screenshots and app preview videos.

Each version directory can hold an `assets/` tree:

    versions/1.4/assets/
    ├── en-US/
    │   ├── screenshots/
    │   │   └── iphone-6.9/
    │   │       ├── 01-record.png
    │   │       └── 02-share.png
    │   └── previews/
    │       └── iphone-6.9/
    │           └── 01-hero.mp4
    └── de-DE/
        └── screenshots/iphone-6.9/01-aufnahme.png

The audit reads the files. It does not send them anywhere. The readers below
use only the standard library: they take the size from the PNG or JPEG header
and the duration from the MP4 header.

App Store Connect shows the assets of a set in file name order. Give each file
a numeric prefix to make the order clear.
"""

import re
import struct
from pathlib import Path

from .model import Suggestion, tokens

ASSET_RULES = [
    'ASSET_MISSING', 'ASSET_ORPHAN', 'ASSET_COUNT', 'ASSET_SIZE', 'ASSET_ALPHA',
    'ASSET_VIDEO_LENGTH', 'ASSET_DEVICE', 'ASSET_ORDER',
    'CAPTION_MISSING', 'CAPTION_LONG', 'CAPTION_KEYWORDS', 'CAPTION_COUNT',
]

# The store indexes the text in a screenshot caption, but a machine cannot read
# the text inside an image. Write the captions in `assets/captions.yaml` and the
# audit can check them:
#
#     locales:
#       en-US:
#         - Download a whole park for offline use
#         - See every metre of climb before you go
#
# A locale can also hold one list per device, when the captions differ.
CAPTIONS_FILE = 'captions.yaml'
CAPTION_MAX_CHARACTERS = 60

SCREENSHOT_EXTENSIONS = {'.png', '.jpg', '.jpeg'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v'}

# Known-good screenshot sizes in pixels, portrait. The landscape size is the
# same pair, reversed. Apple changes these lists. Add your own sizes with
# `assets.device_sizes` in aso.yaml.
DEVICE_SIZES = {
    'iphone-6.9': [(1320, 2868), (1290, 2796)],
    'iphone-6.7': [(1290, 2796), (1284, 2778)],
    'iphone-6.5': [(1242, 2688), (1284, 2778)],
    'iphone-6.1': [(1179, 2556), (1170, 2532)],
    'iphone-5.5': [(1242, 2208)],
    'ipad-13': [(2064, 2752), (2048, 2732)],
    'ipad-12.9': [(2048, 2732)],
    'ipad-11': [(1668, 2388), (1640, 2360)],
    'mac': [(1280, 800), (1440, 900), (2560, 1600), (2880, 1800)],
}

# App preview videos must be between 15 and 30 seconds long.
PREVIEW_MIN_SECONDS = 15
PREVIEW_MAX_SECONDS = 30

_NUMERIC_PREFIX = re.compile(r'^\d+')


def normalize_device(name):
    """Make a device directory name uniform: 'iPhone 6.9' -> 'iphone-6.9'."""
    text = str(name).strip().lower()
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


# -- readers ------------------------------------------------------------------

def png_info(path):
    """(width, height, has_alpha) of a PNG file, or None."""
    with open(path, 'rb') as handle:
        header = handle.read(33)
    if len(header) < 33 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        return None
    width, height = struct.unpack('>II', header[16:24])
    color_type = header[25]
    return width, height, color_type in (4, 6)


def jpeg_size(path):
    """(width, height) of a JPEG file, or None."""
    with open(path, 'rb') as handle:
        if handle.read(2) != b'\xff\xd8':
            return None
        while True:
            marker = handle.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                return None
            code = marker[1]
            if code in (0xD8, 0xD9) or 0xD0 <= code <= 0xD7:
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) < 2:
                return None
            length = struct.unpack('>H', length_bytes)[0]
            if code in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                body = handle.read(5)
                if len(body) < 5:
                    return None
                height, width = struct.unpack('>HH', body[1:5])
                return width, height
            handle.seek(length - 2, 1)


def image_info(path):
    """(width, height, has_alpha) for a PNG or a JPEG, or None."""
    suffix = Path(path).suffix.lower()
    try:
        if suffix == '.png':
            return png_info(path)
        if suffix in ('.jpg', '.jpeg'):
            size = jpeg_size(path)
            return (size[0], size[1], False) if size else None
    except (OSError, struct.error):
        return None
    return None


def mp4_duration(path):
    """Duration of an MP4 or MOV file in seconds, or None.

    The reader walks the top-level atoms, enters `moov`, and reads `mvhd`.
    It returns None for any file that it does not understand.
    """
    try:
        with open(path, 'rb') as handle:
            end = Path(path).stat().st_size
            position = 0
            while position < end:
                handle.seek(position)
                header = handle.read(8)
                if len(header) < 8:
                    return None
                size = struct.unpack('>I', header[:4])[0]
                kind = header[4:8]
                if size == 1:                       # 64-bit size
                    extended = handle.read(8)
                    if len(extended) < 8:
                        return None
                    size = struct.unpack('>Q', extended)[0]
                if size < 8:
                    return None
                if kind == b'moov':
                    moov_end = position + size
                    inner = handle.tell()
                    while inner < moov_end:
                        handle.seek(inner)
                        sub = handle.read(8)
                        if len(sub) < 8:
                            return None
                        sub_size = struct.unpack('>I', sub[:4])[0]
                        if sub_size < 8:
                            return None
                        if sub[4:8] == b'mvhd':
                            body = handle.read(20)
                            if len(body) < 20:
                                return None
                            version = body[0]
                            if version == 1:
                                extra = handle.read(12)
                                if len(extra) < 12:
                                    return None
                                blob = body[4:] + extra
                                timescale = struct.unpack('>I', blob[16:20])[0]
                                duration = struct.unpack('>Q', blob[20:28])[0]
                            else:
                                timescale = struct.unpack('>I', body[12:16])[0]
                                duration = struct.unpack('>I', body[16:20])[0]
                            return duration / timescale if timescale else None
                        inner += sub_size
                    return None
                position += size
    except (OSError, struct.error):
        return None
    return None


# -- the tree -----------------------------------------------------------------

def _sets_in(kind_dir, extensions):
    """{device: [paths]} below one `screenshots/` or `previews/` directory."""
    sets = {}
    direct = sorted(p for p in kind_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in extensions)
    if direct:
        sets['unspecified'] = direct
    for device_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
        files = sorted(p for p in device_dir.rglob('*')
                       if p.is_file() and p.suffix.lower() in extensions)
        if files:
            sets[normalize_device(device_dir.name)] = files
    return sets


def scan(assets_dir):
    """Read the asset tree: {locale: {'screenshots': {...}, 'previews': {...}}}."""
    assets_dir = Path(assets_dir)
    out = {}
    if not assets_dir.is_dir():
        return out
    for locale_dir in sorted(p for p in assets_dir.iterdir()
                             if p.is_dir() and not p.name.startswith('.')):
        entry = {'screenshots': {}, 'previews': {}}
        for kind, extensions in (('screenshots', SCREENSHOT_EXTENSIONS),
                                 ('previews', VIDEO_EXTENSIONS)):
            kind_dir = locale_dir / kind
            if kind_dir.is_dir():
                entry[kind] = _sets_in(kind_dir, extensions)
        if entry['screenshots'] or entry['previews']:
            out[locale_dir.name] = entry
    return out


# -- rules --------------------------------------------------------------------

def read_captions(assets_dir):
    """{locale: {device: [caption]}} from `assets/captions.yaml`, or None.

    A locale can hold a plain list, which then applies to every device. The
    function returns None when the file does not exist, because the caption
    rules are a feature that you switch on by writing the file.
    """
    from . import yamlio

    path = Path(assets_dir) / CAPTIONS_FILE
    if not path.is_file():
        return None
    data = yamlio.load_path(path)
    block = (data or {}).get('locales') or {}
    out = {}
    for code, value in block.items():
        if isinstance(value, dict):
            out[str(code)] = {normalize_device(device): [str(c) for c in (items or [])]
                              for device, items in value.items()}
        elif isinstance(value, list):
            out[str(code)] = {'*': [str(c) for c in value]}
    return out


def _check_captions(tree, captions, settings, phrase_words, primary_locale):
    """The rules for the caption text of the screenshots.

    The store indexes the text in a screenshot caption. A machine cannot read
    the text inside an image, so these rules read `captions.yaml` instead. No
    file means that you do not use the feature, and the rules stay quiet.
    """
    if captions is None:
        return []
    out = []
    required = set(settings.required_locales or ([primary_locale] if primary_locale
                                                 else []))
    for code, entry in sorted(tree.items()):
        shots = entry.get('screenshots') or {}
        if not shots:
            continue
        declared = captions.get(code) or {}
        if not declared:
            if code in required:
                out.append(Suggestion(
                    'CAPTION_MISSING', code, code, 'LOW',
                    f'{code}: the screenshots have no caption text in captions.yaml',
                    detail='The store indexes the words in a screenshot caption, and '
                           'this tool cannot read the text inside an image. Write the '
                           'captions in assets/captions.yaml and the audit can check '
                           'them.',
                    fix=f'Add a `{code}:` block to assets/{CAPTIONS_FILE} with one '
                        'line per screenshot.',
                ))
            continue

        every = [caption for group in declared.values() for caption in group]
        long_ones = [c for c in every if len(c) > CAPTION_MAX_CHARACTERS]
        if long_ones:
            out.append(Suggestion(
                'CAPTION_LONG', f'{code}:{len(long_ones)}', code, 'LOW',
                f'{code}: {len(long_ones)} caption(s) are longer than '
                f'{CAPTION_MAX_CHARACTERS} characters',
                detail='; '.join(f'"{c[:70]}" ({len(c)})' for c in long_ones[:3])
                       + '. A user reads a screenshot in about one second.',
                fix='Cut each caption to one short statement of a benefit.',
            ))

        for device, group in sorted(declared.items()):
            if device == '*':
                counts = {len(files) for files in shots.values()}
                if counts and len(group) not in counts:
                    out.append(Suggestion(
                        'CAPTION_COUNT', f'{code}:*', code, 'LOW',
                        f'{code}: {len(group)} caption(s) for '
                        f'{"/".join(str(c) for c in sorted(counts))} screenshot(s)',
                        fix='Write one caption per screenshot, in the display order.',
                    ))
            elif device in shots and len(group) != len(shots[device]):
                out.append(Suggestion(
                    'CAPTION_COUNT', f'{code}:{device}', code, 'LOW',
                    f'{code}/{device}: {len(group)} caption(s) for '
                    f'{len(shots[device])} screenshot(s)',
                    fix='Write one caption per screenshot, in the display order.',
                ))

        if phrase_words:
            words = set()
            for caption in every:
                words.update(tokens(caption))
            if not (words & set(phrase_words)):
                out.append(Suggestion(
                    'CAPTION_KEYWORDS', code, code, 'MEDIUM',
                    f'{code}: no caption holds a word of your target phrases',
                    detail='The store indexes caption text. A caption that only says '
                           '"Beautiful design" spends indexed characters on nothing, '
                           'and it tells the user nothing either.',
                    fix='Write real search phrases in the captions, for example the '
                        f'words: {", ".join(sorted(phrase_words)[:6])}.',
                ))
    return out


def audit(assets_dir, locales, settings, primary_locale='en-US', phrase_words=()):
    """Return the suggestions for the asset tree of one version."""
    out = []
    tree = scan(assets_dir)
    sizes = dict(DEVICE_SIZES)
    sizes.update(settings.device_sizes or {})

    required = settings.required_locales or ([primary_locale] if primary_locale else [])
    for code in required:
        if code not in tree:
            out.append(Suggestion(
                'ASSET_MISSING', code, code, 'MEDIUM',
                f'{code}: no screenshots in this version',
                detail='The App Store shows the screenshots of the primary language when a '
                       'locale has none. Localized screenshots with translated captions '
                       'convert better, and the store indexes the caption text.',
                fix=f'Add files to assets/{code}/screenshots/<device>/.',
            ))

    for code, entry in sorted(tree.items()):
        if locales and code not in locales:
            out.append(Suggestion(
                'ASSET_ORPHAN', code, code, 'LOW',
                f'{code}: the assets directory has no metadata locale',
                detail='The version has assets for this locale but no YAML metadata. '
                       'The name of the directory must be an App Store locale code, for '
                       'example en-US or de-DE.',
                fix=f'Rename assets/{code}/ or add the locale to the metadata YAML.',
            ))

        for device, files in sorted(entry['screenshots'].items()):
            out.extend(_check_screenshot_set(code, device, files, sizes, settings))
        for device, files in sorted(entry['previews'].items()):
            out.extend(_check_preview_set(code, device, files, settings))

    out.extend(_check_captions(tree, read_captions(assets_dir), settings,
                               set(phrase_words or ()), primary_locale))
    return out


def _order_problem(code, kind, device, files):
    unnumbered = [f.name for f in files if not _NUMERIC_PREFIX.match(f.name)]
    if len(files) < 2 or not unnumbered:
        return []
    return [Suggestion(
        'ASSET_ORDER', f'{code}:{kind}:{device}', code, 'LOW',
        f'{code}/{device}: the {kind} file names do not show the order',
        detail='App Store Connect uses the file name order. Names without a number can '
               'change the order when you add a file.',
        fix='Rename the files with a numeric prefix: 01-…, 02-…, 03-….',
    )]


def _check_screenshot_set(code, device, files, sizes, settings):
    out = []
    if len(files) > settings.max_screenshots:
        out.append(Suggestion(
            'ASSET_COUNT', f'{code}:screenshots:{device}', code, 'CRITICAL',
            f'{code}/{device}: {len(files)} screenshots — the limit is '
            f'{settings.max_screenshots}',
            detail='App Store Connect refuses a set that is too large.',
            fix=f'Keep the best {settings.max_screenshots} images. The first three images '
                'do most of the work.',
        ))
    if device == 'unspecified':
        out.append(Suggestion(
            'ASSET_DEVICE', f'{code}:screenshots:unspecified', code, 'LOW',
            f'{code}: the screenshots are not in a device directory',
            detail='Every screenshot set belongs to one device size.',
            fix='Move the files to screenshots/<device>/, for example '
                'screenshots/iphone-6.9/.',
        ))
    elif device not in sizes:
        out.append(Suggestion(
            'ASSET_DEVICE', f'{code}:screenshots:{device}', code, 'LOW',
            f'{code}: the device directory "{device}" is not known',
            detail='The tool knows these device names: ' + ', '.join(sorted(sizes)) + '.',
            fix='Rename the directory, or add the size to `assets.device_sizes` in aso.yaml.',
        ))
    out.extend(_order_problem(code, 'screenshot', device, files))

    if not settings.check_dimensions:
        return out
    allowed = sizes.get(device)
    bad_size, alpha = [], []
    for file in files:
        info = image_info(file)
        if info is None:
            continue
        width, height, has_alpha = info
        if has_alpha:
            alpha.append(file.name)
        if allowed and (width, height) not in allowed and (height, width) not in allowed:
            bad_size.append(f'{file.name} ({width}×{height})')
    if bad_size:
        want = ' or '.join(f'{w}×{h}' for w, h in allowed)
        out.append(Suggestion(
            'ASSET_SIZE', f'{code}:{device}:{",".join(sorted(bad_size))}', code, 'HIGH',
            f'{code}/{device}: {len(bad_size)} screenshot(s) have an unexpected size',
            detail=', '.join(sorted(bad_size)) + f'. The set expects {want}, in portrait or '
                                                 'in landscape.',
            fix='Export the images again at the correct size, or correct the device '
                'directory name.',
        ))
    if alpha:
        out.append(Suggestion(
            'ASSET_ALPHA', f'{code}:{device}:{",".join(sorted(alpha))}', code, 'HIGH',
            f'{code}/{device}: {len(alpha)} screenshot(s) have an alpha channel',
            detail=', '.join(sorted(alpha)) + '. App Store Connect refuses images with '
                                              'transparency.',
            fix='Export the images again without an alpha channel, or flatten them on a '
                'solid background.',
        ))
    return out


def _check_preview_set(code, device, files, settings):
    out = []
    if len(files) > settings.max_previews:
        out.append(Suggestion(
            'ASSET_COUNT', f'{code}:previews:{device}', code, 'CRITICAL',
            f'{code}/{device}: {len(files)} app previews — the limit is '
            f'{settings.max_previews}',
            fix=f'Keep {settings.max_previews} videos or fewer in the set.',
        ))
    out.extend(_order_problem(code, 'preview', device, files))
    if not settings.check_video_duration:
        return out
    bad = []
    for file in files:
        seconds = mp4_duration(file)
        if seconds is None:
            continue
        if seconds < PREVIEW_MIN_SECONDS or seconds > PREVIEW_MAX_SECONDS:
            bad.append(f'{file.name} ({seconds:.1f}s)')
    if bad:
        out.append(Suggestion(
            'ASSET_VIDEO_LENGTH', f'{code}:{device}:{",".join(sorted(bad))}', code, 'HIGH',
            f'{code}/{device}: {len(bad)} app preview(s) are outside 15–30 seconds',
            detail=', '.join(sorted(bad)) + '. App Store Connect accepts a preview between '
                                            f'{PREVIEW_MIN_SECONDS} and '
                                            f'{PREVIEW_MAX_SECONDS} seconds.',
            fix='Cut the video to the accepted length.',
        ))
    return out


def summary(assets_dir):
    """A short table of the asset tree, for the `aso assets` command."""
    tree = scan(assets_dir)
    rows = []
    for code, entry in sorted(tree.items()):
        for kind in ('screenshots', 'previews'):
            for device, files in sorted(entry[kind].items()):
                rows.append((code, kind, device, len(files)))
    return rows
