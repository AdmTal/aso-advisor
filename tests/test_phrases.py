"""Tests for the phrase generator. The autocomplete is replaced by a fixture."""

import pytest

from aso_advisor import db, phrases, store_api, workspace
from conftest import write_workspace

CONFIG = """\
version: 1
app:
  name: Trailwise
  track_id: 111
  primary_locale: en-US
  default_country: us
markets:
  storefront_groups: [US]
"""

STRATEGY = """\
brand_phrases: [trailwise]
seed_keywords:
  - term: hike
    score: 9
    why: The category word.
phrase_targets:
  - phrase: offline hiking maps
    score: 9
discovery_seeds: [hiking]
low_value_terms: [free, iphone, app]
trademark_terms: [rivalapp]
"""

VERSION = """\
locales:
  en-US:
    language: English
    name: 'Trailwise: Hike GPS'
    subtitle: Offline Maps
    keywords: compass,elevation
"""

SUGGESTIONS = {
    'hiking': [
        'hiking maps',              # 1
        'hiking gps tracker',       # 2
        'hiking',                   # 3 — one word, becomes a seed proposal
        'hiking app free',          # 4 — low value words
        'hiking maps: pro edition',  # 5 — the name of an app
        'hiking hiking trail',      # 6 — a repeated word, also a name
        'compass',                  # 7 — one word that we already index
    ],
    'hike': ['hike tracker', 'hiking maps'],
    'offline hiking maps': ['offline hiking maps free'],
}


@pytest.fixture
def ws(tmp_path):
    root = write_workspace(tmp_path / 'aso', config=CONFIG, strategy=STRATEGY,
                           versions={'1.0': {'titles.yaml': VERSION}})
    return workspace.load(explicit=str(root))


@pytest.fixture
def conn():
    connection = db.connect_memory()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    def hints(_conn, term, country='us', ttl_hours=12):
        return SUGGESTIONS.get(term, [])
    monkeypatch.setattr(store_api, 'hints', hints)
    monkeypatch.setattr(store_api, 'lookup', lambda *a, **k: [])
    monkeypatch.setattr(store_api, 'reviews', lambda *a, **k: [])


def by_phrase(rows):
    return {row['phrase']: row for row in rows}


# -- generation ---------------------------------------------------------------

def test_the_roots_come_from_seeds_phrases_and_discovery(ws):
    roots = phrases.collect_roots(ws)
    assert 'hiking' in roots            # discovery_seeds
    assert 'hike' in roots              # a strong seed keyword
    assert 'offline hiking maps' in roots   # an existing target


def test_extra_roots_come_first(ws):
    assert phrases.collect_roots(ws, ['trail map'])[0] == 'trail map'


def test_candidates_come_from_the_autocomplete(ws, conn):
    candidates, _seeds = phrases.generate(ws, conn)
    found = by_phrase(candidates)
    assert 'hiking maps' in found
    assert 'hiking gps tracker' in found


def test_the_position_drives_the_score(ws, conn):
    found = by_phrase(phrases.generate(ws, conn)[0])
    assert found['hiking maps']['score'] > found['hiking gps tracker']['score']


def test_a_phrase_that_you_already_target_is_not_proposed_again(ws, conn):
    assert 'offline hiking maps' not in by_phrase(phrases.generate(ws, conn)[0])


def test_the_name_of_an_app_is_not_a_phrase(ws, conn):
    found = by_phrase(phrases.generate(ws, conn)[0])
    assert 'hiking maps: pro edition' not in found      # a colon
    assert 'hiking hiking trail' not in found           # a repeated word


def test_low_value_words_lower_the_score(ws, conn):
    found = by_phrase(phrases.generate(ws, conn)[0])
    assert 'low value' in '; '.join(found['hiking app free']['reasons'])
    assert found['hiking app free']['score'] < found['hiking maps']['score']


def test_coverage_says_what_is_missing(ws, conn):
    found = by_phrase(phrases.generate(ws, conn)[0])
    row = found['hiking gps tracker']
    assert row['covered_by'] is None
    assert set(row['missing']) == {'hiking', 'tracker'}
    assert row['nearest'] == 'en-US'


def test_a_word_that_we_do_not_index_becomes_a_seed_proposal(ws, conn):
    _candidates, seeds = phrases.generate(ws, conn)
    terms = [seed['term'] for seed in seeds]
    assert 'hiking' in terms        # one word, not indexed
    assert 'compass' not in terms   # one word, already in the keyword field


def test_a_competitor_title_adds_a_phrase_and_a_reason(ws, conn, monkeypatch):
    (ws.strategy.competitors).update({777: 'Rival'})
    monkeypatch.setattr(store_api, 'lookup', lambda *a, **k: [
        {'trackId': 777, 'trackName': 'Rival Maps: Offline Trail Navigation'}])
    found = by_phrase(phrases.generate(ws, conn)[0])
    assert 'offline trail navigation' in found
    assert any('title of' in reason
               for reason in found['offline trail navigation']['reasons'])


def test_review_words_become_seed_proposals(ws, conn, monkeypatch):
    monkeypatch.setattr(store_api, 'reviews', lambda *a, **k: [
        {'title': 'Great', 'body': 'the waypoints are perfect', 'rating': 5,
         'version': '1', 'date': '2026-07-01', 'author': 'a', 'country': 'us'}
        for _ in range(4)])
    _candidates, seeds = phrases.generate(ws, conn, with_reviews=True)
    assert 'waypoints' in [seed['term'] for seed in seeds]


def test_a_trademark_lowers_the_score(ws, conn, monkeypatch):
    monkeypatch.setattr(store_api, 'hints', lambda _c, term, **k:
                        ['rivalapp alternative'] if term == 'hiking' else [])
    found = by_phrase(phrases.generate(ws, conn)[0])
    row = found['rivalapp alternative']
    assert row['risky'] == ['rivalapp']
    assert row['score'] <= 8


def test_the_limit_is_respected(ws, conn):
    candidates, _seeds = phrases.generate(ws, conn, limit=2)
    assert len(candidates) == 2


def test_a_storefront_with_no_answer_returns_nothing(ws, conn, monkeypatch):
    monkeypatch.setattr(store_api, 'hints', lambda *a, **k: [])
    assert phrases.generate(ws, conn) == ([], [])


# -- writing back -------------------------------------------------------------

def test_write_adds_the_strong_proposals(ws, conn):
    candidates, _seeds = phrases.generate(ws, conn)
    added, _block = phrases.write_phrases(ws, candidates, minimum_score=6)
    assert added
    reloaded = workspace.load(explicit=str(ws.root))
    targets = {p for p, _s, _w in reloaded.strategy.phrase_targets}
    assert 'offline hiking maps' in targets      # what was there stays
    assert 'hiking maps' in targets              # the new one is there


def test_write_does_not_repeat_a_phrase(ws, conn):
    candidates, _seeds = phrases.generate(ws, conn)
    phrases.write_phrases(ws, candidates, minimum_score=6)
    again = workspace.load(explicit=str(ws.root))
    added, _block = phrases.write_phrases(again, candidates, minimum_score=6)
    assert added == []


def test_write_keeps_the_rest_of_the_file(ws, conn):
    candidates, _seeds = phrases.generate(ws, conn)
    phrases.write_phrases(ws, candidates, minimum_score=6)
    text = ws.strategy_path.read_text(encoding='utf-8')
    assert 'brand_phrases: [trailwise]' in text
    assert 'trademark_terms: [rivalapp]' in text
    reloaded = workspace.load(explicit=str(ws.root))
    assert reloaded.strategy.seed_keywords == [('hike', 9, 'The category word.')]


def test_write_seeds_adds_the_words(ws, conn):
    _candidates, seeds = phrases.generate(ws, conn)
    added, _block = phrases.write_seeds(ws, seeds)
    assert added
    reloaded = workspace.load(explicit=str(ws.root))
    terms = {t for t, _s, _w in reloaded.strategy.seed_keywords}
    assert 'hike' in terms and 'hiking' in terms


def test_merge_makes_the_key_when_the_file_has_none(tmp_path):
    path = tmp_path / 'strategy.yaml'
    path.write_text('brand_phrases: [x]\n', encoding='utf-8')
    phrases.merge_into_strategy(path, 'phrase_targets', [('a b', 7, '')], 'phrase')
    text = path.read_text(encoding='utf-8')
    assert 'brand_phrases: [x]' in text
    assert 'phrase_targets:' in text
    assert '- phrase: a b' in text


def test_merge_keeps_the_key_that_follows(tmp_path):
    path = tmp_path / 'strategy.yaml'
    path.write_text('phrase_targets: []\n\n# a comment\nlow_value_terms: [free]\n',
                    encoding='utf-8')
    phrases.merge_into_strategy(path, 'phrase_targets', [('a b', 7, 'why')], 'phrase')
    text = path.read_text(encoding='utf-8')
    assert '# a comment' in text
    assert 'low_value_terms: [free]' in text
    assert 'why: why' in text
