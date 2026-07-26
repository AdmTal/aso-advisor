from aso_advisor import loader, writer

EXISTING_TITLES = """\
# my own comment
locales:
  de-DE:
    language: German
    name: Alter Name
    name_eng: Old Name
    subtitle: Alter Untertitel
    subtitle_eng: Old subtitle
    keywords: karte,berg
"""


def test_write_makes_the_two_default_files(tmp_path):
    written = writer.write_version(tmp_path, {
        'en-US': {'name': 'Trailwise', 'subtitle': 'Offline Maps', 'keywords': 'gps',
                  'description': 'What the app does.', 'promotional_text': 'Try it.'}})
    names = sorted(p.name for p in written)
    assert names == ['descriptions.yaml', 'titles_and_keywords.yaml']
    back = loader.load_version_raw(tmp_path)
    assert back['en-US']['name'] == 'Trailwise'
    assert back['en-US']['description'] == 'What the app does.'


def test_write_keeps_the_language_note_and_the_back_translation(tmp_path):
    (tmp_path / 'titles_and_keywords.yaml').write_text(EXISTING_TITLES, encoding='utf-8')
    writer.write_version(tmp_path, {'de-DE': {'name': 'Neuer Name', 'keywords': 'karte'}})
    text = (tmp_path / 'titles_and_keywords.yaml').read_text(encoding='utf-8')
    assert 'language: German' in text
    assert 'name_eng: Old Name' in text        # the note stays
    assert 'Neuer Name' in text                # the value is new
    assert 'Alter Name' not in text


def test_write_keeps_the_file_names_that_the_directory_uses(tmp_path):
    (tmp_path / 'titles_and_keys.yaml').write_text(EXISTING_TITLES, encoding='utf-8')
    (tmp_path / 'descriptions_and_links.yaml').write_text(
        'locales:\n  de-DE:\n    description: Alt\n', encoding='utf-8')
    written = writer.write_version(tmp_path, {
        'de-DE': {'name': 'Neu', 'description': 'Neu beschrieben'}})
    assert sorted(p.name for p in written) == ['descriptions_and_links.yaml',
                                               'titles_and_keys.yaml']
    assert not (tmp_path / 'titles_and_keywords.yaml').exists()


def test_a_single_file_layout_stays_a_single_file(tmp_path):
    (tmp_path / 'metadata.yaml').write_text(
        'locales:\n  en-US:\n    name: A\n    description: B\n', encoding='utf-8')
    written = writer.write_version(tmp_path, {
        'en-US': {'name': 'New name', 'description': 'New description',
                  'keywords': 'gps'}})
    assert [p.name for p in written] == ['metadata.yaml']
    back = loader.load_version_raw(tmp_path)
    assert back['en-US'] == {'name': 'New name', 'keywords': 'gps',
                             'description': 'New description'}


def test_long_text_is_written_as_a_block(tmp_path):
    writer.write_version(tmp_path, {'en-US': {'description': 'One.\n\nTwo.\n\nThree.'}})
    text = (tmp_path / 'descriptions.yaml').read_text(encoding='utf-8')
    assert 'description: |-' in text


def test_the_urls_belong_to_the_description_file(tmp_path):
    writer.write_version(tmp_path, {
        'en-US': {'name': 'A', 'support_url': 'https://example.test/support'}})
    assert 'support_url' in (tmp_path / 'descriptions.yaml').read_text(encoding='utf-8')


def test_locales_are_written_in_order(tmp_path):
    writer.write_version(tmp_path, {'de-DE': {'name': 'B'}, 'en-US': {'name': 'A'},
                                    'ar-SA': {'name': 'C'}})
    text = (tmp_path / 'titles_and_keywords.yaml').read_text(encoding='utf-8')
    assert text.index('ar-SA') < text.index('de-DE') < text.index('en-US')
