"""The YAML loader must not turn `no` into a boolean. Norway depends on it."""

from aso_advisor import yamlio


def test_country_and_locale_codes_stay_text():
    data = yamlio.load('markets:\n  rank_countries: [us, no, gb]\n')
    assert data['markets']['rank_countries'] == ['us', 'no', 'gb']


def test_a_locale_key_stays_text():
    data = yamlio.load('locale_priority:\n  no: Norway\n  se: Sweden\n')
    assert data['locale_priority'] == {'no': 'Norway', 'se': 'Sweden'}


def test_stopwords_stay_text():
    data = yamlio.load('phrase_stopwords: [with, on, no, off, yes]\n')
    assert data['phrase_stopwords'] == ['with', 'on', 'no', 'off', 'yes']


def test_real_booleans_still_work():
    data = yamlio.load('assets:\n  check: true\n  check_dimensions: false\n')
    assert data['assets'] == {'check': True, 'check_dimensions': False}


def test_numbers_and_text_are_unchanged():
    data = yamlio.load('app:\n  track_id: 123456789\n  name: Trailwise\n')
    assert data['app']['track_id'] == 123456789
    assert data['app']['name'] == 'Trailwise'


def test_load_path_of_a_missing_file(tmp_path):
    assert yamlio.load_path(tmp_path / 'nothing.yaml') == {}


def test_the_workspace_keeps_norway(tmp_path):
    from aso_advisor import workspace

    root = tmp_path / 'aso'
    root.mkdir()
    (root / 'aso.yaml').write_text('markets:\n  rank_countries: [us, no]\n')
    (root / 'strategy.yaml').write_text('locale_priority:\n  no: Norway\n')
    ws = workspace.load(explicit=str(root))
    assert ws.config.rank_countries == ['us', 'no']
    assert ws.strategy.locale_priority == {'no': 'Norway'}
