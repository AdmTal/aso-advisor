import pytest

from aso_advisor import loader

TITLES = """\
locales:
  en-US:
    language: English
    name: Trailwise
    subtitle: Offline Maps
    keywords: gps,compass
  de-DE:
    language: German
    name: Trailwise DE
    name_eng: Trailwise DE (back translation)
    keywords: karte
"""

DESCRIPTIONS = """\
locales:
  en-US:
    description: What the app does.
    promotional_text: Try it.
    whats_new: Faster maps.
"""


def _version(tmp_path, name, files):
    directory = tmp_path / 'versions' / name
    directory.mkdir(parents=True)
    for filename, text in files.items():
        (directory / filename).write_text(text, encoding='utf-8')
    return directory


def test_discover_versions_sorts_numerically(tmp_path):
    for name in ('2.10', '2.2', '10.0', '2.1'):
        _version(tmp_path, name, {'titles.yaml': TITLES})
    names = [n for n, _p in loader.discover_versions(tmp_path / 'versions')]
    assert names == ['2.1', '2.2', '2.10', '10.0']


def test_discover_versions_skips_empty_and_hidden(tmp_path):
    _version(tmp_path, '1.0', {'titles.yaml': TITLES})
    (tmp_path / 'versions' / 'notes').mkdir()
    (tmp_path / 'versions' / 'notes' / 'readme.txt').write_text('x')
    (tmp_path / 'versions' / '.hidden').mkdir()
    assert [n for n, _p in loader.discover_versions(tmp_path / 'versions')] == ['1.0']


def test_discover_versions_of_missing_directory():
    assert loader.discover_versions('/nowhere/at/all') == []


def test_load_version_merges_every_file(tmp_path):
    path = _version(tmp_path, '1.0', {'titles.yaml': TITLES, 'descriptions.yaml': DESCRIPTIONS})
    locales = loader.load_version(path)
    assert set(locales) == {'en-US', 'de-DE'}
    assert locales['en-US'].keywords == 'gps,compass'
    assert locales['en-US'].description == 'What the app does.'
    assert locales['en-US'].promotional_text == 'Try it.'
    assert locales['de-DE'].language == 'German'


def test_load_version_ignores_back_translations(tmp_path):
    path = _version(tmp_path, '1.0', {'titles.yaml': TITLES})
    assert loader.load_version(path)['de-DE'].name == 'Trailwise DE'


def test_load_version_accepts_field_aliases(tmp_path):
    path = _version(tmp_path, '1.0', {'m.yaml': 'locales:\n  en-US:\n    title: Alias\n'
                                                '    release_notes: Notes\n'})
    meta = loader.load_version(path)['en-US']
    assert meta.name == 'Alias'
    assert meta.whats_new == 'Notes'


def test_load_version_without_locales_block(tmp_path):
    path = _version(tmp_path, '1.0', {'other.yaml': 'something: else\n'})
    with pytest.raises(loader.MetadataError, match='locales'):
        loader.load_version(path)


def test_load_version_with_broken_yaml(tmp_path):
    path = _version(tmp_path, '1.0', {'m.yaml': 'locales:\n  en-US:\n   - [unclosed\n'})
    with pytest.raises(loader.MetadataError, match='not valid YAML'):
        loader.load_version(path)


def test_select_and_previous_version(tmp_path):
    for name in ('1.0', '1.1', '1.2'):
        _version(tmp_path, name, {'titles.yaml': TITLES})
    versions = loader.discover_versions(tmp_path / 'versions')
    assert loader.select_version(versions)[0] == '1.2'
    assert loader.select_version(versions, '1.1')[0] == '1.1'
    assert loader.previous_version(versions, '1.1')[0] == '1.0'
    assert loader.previous_version(versions, '1.0') == (None, None)
    with pytest.raises(loader.MetadataError, match='not in the workspace'):
        loader.select_version(versions, '9.9')


def test_select_version_without_any_version():
    with pytest.raises(loader.MetadataError, match='No metadata version'):
        loader.select_version([])
