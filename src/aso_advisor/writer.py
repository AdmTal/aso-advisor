"""Write metadata YAML back into a version directory.

`aso pull` uses this module. It keeps the two things that a machine must not
lose: the `language:` note of each locale, and every `*_eng` back-translation
that you wrote for review.

The default layout is two files, `titles_and_keywords.yaml` and
`descriptions.yaml`. If the directory already has other file names, the writer
keeps them, so a repository that came from another tool does not change shape.
"""

from pathlib import Path

import yaml

from . import yamlio

TITLES_FILE = 'titles_and_keywords.yaml'
DESCRIPTIONS_FILE = 'descriptions.yaml'

TITLE_FIELDS = ('name', 'subtitle', 'keywords')
DESCRIPTION_FIELDS = ('description', 'promotional_text', 'whats_new',
                      'marketing_url', 'support_url', 'privacy_policy_url')

TITLES_HEADER = """\
# Titles, subtitles, and keyword fields, one block per App Store locale.
# Limits: name 30, subtitle 30, keywords 100 characters.
# The keyword field holds single words, separated by commas, with no spaces.
# `language:` and every `*_eng` field are notes for the reader. The tool and
# App Store Connect both ignore them.

"""

DESCRIPTIONS_HEADER = """\
# Descriptions, promotional text, release notes, and URLs.
# Limits: description 4000, promotional_text 170, whats_new 4000 characters.
# The promotional text is the one field that you can change without a release.

"""

MERGED_HEADER = """\
# App Store metadata, one block per locale.
# Limits: name 30, subtitle 30, keywords 100, promotional_text 170,
# description 4000, whats_new 4000 characters.

"""


class _Literal(str):
    """A marker so that PyYAML writes long text as a block."""


def _literal_representer(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', str(data), style='|')


yaml.add_representer(_Literal, _literal_representer)


def _maybe_literal(value):
    if isinstance(value, str) and ('\n' in value or len(value) > 80):
        return _Literal(value)
    return value


def _dump(document):
    return yaml.dump(document, sort_keys=False, allow_unicode=True, width=200,
                     default_flow_style=False)


def _read_raw(path):
    if not Path(path).is_file():
        return {'locales': {}}
    data = yamlio.load(Path(path).read_text(encoding='utf-8')) or {}
    if not isinstance(data, dict):
        return {'locales': {}}
    data.setdefault('locales', {})
    return data


def detect_layout(directory):
    """Which file holds which fields. Returns (titles_path, descriptions_path).

    Both paths can be the same file when the directory keeps everything
    together.
    """
    directory = Path(directory)
    titles_path = descriptions_path = None
    for path in sorted([*directory.glob('*.yaml'), *directory.glob('*.yml')]):
        raw = _read_raw(path)
        keys = set()
        for fields in (raw.get('locales') or {}).values():
            if isinstance(fields, dict):
                keys.update(fields)
        if titles_path is None and keys & set(TITLE_FIELDS):
            titles_path = path
        if descriptions_path is None and keys & set(DESCRIPTION_FIELDS):
            descriptions_path = path
    return (titles_path or directory / TITLES_FILE,
            descriptions_path or directory / DESCRIPTIONS_FILE)


def _entry(existing, fields, order):
    """One locale block: the language note, then each field and its `_eng` twin."""
    out = {}
    language = existing.get('language')
    if language is not None:
        out['language'] = language
    for key in order:
        if key in fields and fields[key] is not None:
            out[key] = _maybe_literal(fields[key])
            twin = f'{key}_eng'
            if twin in existing:
                out[twin] = _maybe_literal(existing[twin])
    return out


def write_version(directory, locales, preserve_from=None):
    """Write `{locale: {field: value}}` into a version directory.

    Returns the list of files that changed on disk.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(preserve_from) if preserve_from else directory
    titles_path, descriptions_path = detect_layout(source if source.is_dir() else directory)
    if source != directory:
        titles_path = directory / titles_path.name
        descriptions_path = directory / descriptions_path.name

    prior_titles = (_read_raw(source / titles_path.name).get('locales') or {})
    prior_descriptions = (_read_raw(source / descriptions_path.name).get('locales') or {})

    merged = titles_path == descriptions_path
    order = TITLE_FIELDS + DESCRIPTION_FIELDS if merged else TITLE_FIELDS
    titles_doc = {'locales': {}}
    descriptions_doc = {'locales': {}}

    for code in sorted(locales, key=str.lower):
        fields = locales[code]
        titles_entry = _entry(prior_titles.get(code, {}), fields, order)
        if titles_entry:
            titles_doc['locales'][code] = titles_entry
        if not merged:
            descriptions_entry = _entry(prior_descriptions.get(code, {}), fields,
                                        DESCRIPTION_FIELDS)
            if descriptions_entry:
                descriptions_doc['locales'][code] = descriptions_entry

    written = []
    if merged:
        titles_path.write_text(MERGED_HEADER + _dump(titles_doc), encoding='utf-8')
        written.append(titles_path)
    else:
        titles_path.write_text(TITLES_HEADER + _dump(titles_doc), encoding='utf-8')
        written.append(titles_path)
        if descriptions_doc['locales']:
            descriptions_path.write_text(DESCRIPTIONS_HEADER + _dump(descriptions_doc),
                                         encoding='utf-8')
            written.append(descriptions_path)
    return written
