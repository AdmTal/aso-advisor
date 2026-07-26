"""Bring metadata from another tool into the workspace.

Today the module reads a `fastlane deliver` metadata tree. That layout is one
directory per locale, and one text file per field:

    fastlane/metadata/
    ├── en-US/
    │   ├── name.txt
    │   ├── subtitle.txt
    │   ├── keywords.txt
    │   ├── description.txt
    │   ├── promotional_text.txt
    │   └── release_notes.txt
    ├── de-DE/…
    └── default/            # values that fill the gaps of every locale

Nothing is deleted and nothing is uploaded. The import writes YAML into a
version directory of the workspace, and then every other command works.
"""

import re
from pathlib import Path

from .storefronts import ASC_LOCALES

# The file name of fastlane -> the field name of the workspace.
FASTLANE_FIELDS = {
    'name': 'name',
    'subtitle': 'subtitle',
    'keywords': 'keywords',
    'description': 'description',
    'promotional_text': 'promotional_text',
    'release_notes': 'whats_new',
    'marketing_url': 'marketing_url',
    'support_url': 'support_url',
    'privacy_url': 'privacy_policy_url',
}

# Directories of a fastlane tree that hold no localized metadata.
NOT_LOCALES = {'default', 'review_information',
               'trade_representative_contact_information'}

LOCALE_SHAPE = re.compile(r'^[a-z]{2,3}(-[A-Za-z]{2,4})?$')


def looks_like_a_locale(name):
    """True for an App Store locale code, or for something very close to one."""
    return name in ASC_LOCALES or bool(LOCALE_SHAPE.match(str(name)))


def read_locale_dir(directory):
    """{field: value} from one directory of text files."""
    out = {}
    for file in sorted(Path(directory).glob('*.txt')):
        field = FASTLANE_FIELDS.get(file.stem)
        if not field:
            continue
        value = file.read_text(encoding='utf-8').strip()
        if value:
            out[field] = value
    return out


def read_fastlane(directory):
    """Read a fastlane metadata tree into {locale: {field: value}}.

    Returns (locales, notes). `notes` holds the lines to show the user.
    """
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        raise FileNotFoundError(f'This directory does not exist: {directory}')

    notes = []
    fallback = {}
    default_dir = directory / 'default'
    if default_dir.is_dir():
        fallback = read_locale_dir(default_dir)
        if fallback:
            notes.append(f'default/ holds {len(fallback)} field(s). They fill the gaps '
                         'of every locale, as fastlane does.')

    locales, skipped = {}, []
    for child in sorted(p for p in directory.iterdir() if p.is_dir()):
        if child.name in NOT_LOCALES:
            continue
        if not looks_like_a_locale(child.name):
            skipped.append(child.name)
            continue
        fields = read_locale_dir(child)
        if not fields:
            continue
        merged = dict(fallback)
        merged.update(fields)
        locales[child.name] = merged
        if child.name not in ASC_LOCALES:
            notes.append(f'{child.name} is not an App Store locale code. Check the '
                         'name before you push.')

    if skipped:
        notes.append('Skipped, because the name is not a locale: '
                     + ', '.join(skipped))

    screenshots = directory.parent / 'screenshots'
    if screenshots.is_dir():
        count = sum(1 for path in screenshots.rglob('*')
                    if path.suffix.lower() in ('.png', '.jpg', '.jpeg'))
        if count:
            notes.append(
                f'{count} screenshot(s) sit in {screenshots}. The workspace keeps them '
                'per version and per device, so copy them to '
                'assets/<locale>/screenshots/<device>/. Then `aso assets` checks the '
                'sizes and `aso push-assets` uploads them.')
    return locales, notes


def cmd_import(ws, fastlane_dir, version=None, force=False):
    """Write an external metadata tree into a version of the workspace."""
    from . import loader, writer

    locales, notes = read_fastlane(fastlane_dir)
    if not locales:
        print(f'No locale directory with metadata under {fastlane_dir}.')
        return 1

    name = version or 'imported'
    target = ws.versions_dir / name
    if target.exists() and not force:
        print(f'{target} exists. Use --metadata-version to name another directory, '
              'or --force to overwrite it.')
        return 1

    written = writer.write_version(target, locales,
                                   preserve_from=target if target.is_dir() else None)
    fields = sum(len(values) for values in locales.values())
    print(f'{len(locales)} locale(s) and {fields} field(s) written into {target}:')
    for path in written:
        print(f'  {path}')
    if notes:
        print()
        for note in notes:
            print(f'  note: {note}')

    versions = loader.discover_versions(ws.versions_dir)
    if versions and versions[-1][0] != name:
        print(f'\nThe newest version of the workspace is still {versions[-1][0]}. '
              f'Use `aso audit --metadata-version {name}` for the import, or rename '
              'the directory to the version number that it belongs to.')
    else:
        print('\nRun `aso audit` to see what the metadata says.')
    return 0
