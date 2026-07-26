"""Read the metadata versions of a workspace.

Each subdirectory of `versions/` is one version. The directory can hold one
YAML file or many. The loader reads every `*.yaml` and `*.yml` file in the
directory and merges the `locales:` block of each file. This keeps the layout
free: you can put the titles and the descriptions in one file, or you can split
them into `titles_and_keywords.yaml` and `descriptions.yaml`.

Fields that end with `_eng` are back-translations for human review. The loader
ignores them.
"""

import re
from pathlib import Path

import yaml

from . import yamlio
from .model import LocaleMeta

FIELD_ALIASES = {
    'name': 'name',
    'title': 'name',
    'subtitle': 'subtitle',
    'keywords': 'keywords',
    'description': 'description',
    'promotional_text': 'promotional_text',
    'promo_text': 'promotional_text',
    'whats_new': 'whats_new',
    'release_notes': 'whats_new',
}


class MetadataError(Exception):
    """A metadata file is missing or is not valid."""


def _version_key(name):
    """Sort key for a version directory name. '5.10' comes after '5.9'."""
    numbers = tuple(int(p) for p in re.findall(r'\d+', name))
    return (numbers or (0,), name)


def discover_versions(versions_dir):
    """Return [(version_name, path)], from the oldest to the newest."""
    versions_dir = Path(versions_dir)
    if not versions_dir.is_dir():
        return []
    found = []
    for directory in versions_dir.iterdir():
        if not directory.is_dir() or directory.name.startswith('.'):
            continue
        if any(directory.glob('*.yaml')) or any(directory.glob('*.yml')):
            found.append((directory.name, directory))
    return sorted(found, key=lambda item: _version_key(item[0]))


def metadata_files(path):
    """Every metadata file of a version directory, in a stable order."""
    path = Path(path)
    files = sorted([*path.glob('*.yaml'), *path.glob('*.yml')])
    return [f for f in files if not f.name.startswith('.')]


def load_version(path):
    """Load one version directory into {locale_code: LocaleMeta}."""
    path = Path(path)
    files = metadata_files(path)
    if not files:
        raise MetadataError(f'No YAML metadata file in {path}.')

    locales = {}
    for file in files:
        try:
            data = yamlio.load(file.read_text(encoding='utf-8')) or {}
        except yaml.YAMLError as exc:
            raise MetadataError(f'{file} is not valid YAML:\n{exc}') from exc
        block = data.get('locales')
        if not isinstance(block, dict):
            continue  # A file without a `locales:` block is not metadata.
        for code, fields in block.items():
            fields = fields or {}
            meta = locales.get(code)
            if meta is None:
                meta = LocaleMeta(code=code, language=str(fields.get('language', code) or code))
                locales[code] = meta
            for raw_key, value in fields.items():
                key = str(raw_key)
                if key.endswith('_eng') or key == 'language':
                    continue
                target = FIELD_ALIASES.get(key)
                if target and value is not None:
                    setattr(meta, target, str(value))
    if not locales:
        raise MetadataError(
            f'No `locales:` block in the YAML files of {path}.\n'
            'Every metadata file needs a top-level `locales:` key. '
            'See docs/workspace.md.')
    return locales


def load_version_raw(path):
    """Load a version directory as plain dictionaries: {locale: {field: value}}.

    `load_version` returns `LocaleMeta` objects for the audit, which hold only
    the fields that the rules read. The push and pull commands need every
    field, the URLs included, so they use this function. Notes for the reader
    (`language:` and every `*_eng` field) are removed.
    """
    path = Path(path)
    files = metadata_files(path)
    if not files:
        raise MetadataError(f'No YAML metadata file in {path}.')
    out = {}
    for file in files:
        try:
            data = yamlio.load(file.read_text(encoding='utf-8')) or {}
        except yaml.YAMLError as exc:
            raise MetadataError(f'{file} is not valid YAML:\n{exc}') from exc
        block = data.get('locales')
        if not isinstance(block, dict):
            continue
        for code, fields in block.items():
            if not isinstance(fields, dict):
                raise MetadataError(f'{file}: locale {code!r} must hold a block of fields.')
            clean = {k: v for k, v in fields.items()
                     if k != 'language' and not str(k).endswith('_eng')}
            out.setdefault(code, {}).update(clean)
    return out


def select_version(versions, wanted=None):
    """Return (name, path) for `wanted`, or the newest version."""
    if not versions:
        raise MetadataError(
            'No metadata version found.\n'
            'Add a directory under versions/, for example versions/1.0/, '
            'and put a YAML file in it. See docs/workspace.md.')
    if not wanted:
        return versions[-1]
    for name, path in versions:
        if name == wanted:
            return name, path
    have = ', '.join(name for name, _ in versions)
    raise MetadataError(f'Version {wanted!r} is not in the workspace. Available: {have}')


def previous_version(versions, current_name):
    """The version before `current_name`, or (None, None)."""
    names = [name for name, _ in versions]
    if current_name not in names:
        return None, None
    index = names.index(current_name)
    if index == 0:
        return None, None
    return versions[index - 1]
