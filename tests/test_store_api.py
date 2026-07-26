"""Tests for the client of the public Apple endpoints.

No test in this file reaches the network. Each one replaces `store_api._get`.
"""

import json
import plistlib

import pytest

from aso_advisor import db, store_api


@pytest.fixture
def conn():
    connection = db.connect_memory()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(store_api.time, 'sleep', lambda _seconds: None)


def fake_get(monkeypatch, body, calls=None):
    def _get(url, headers=None):
        if calls is not None:
            calls.append((url, headers))
        return body if isinstance(body, str) else body(url, headers)
    monkeypatch.setattr(store_api, '_get', _get)


SEARCH_BODY = json.dumps({'resultCount': 2, 'results': [
    {'trackId': 111, 'trackName': 'Rival'},
    {'trackId': 222, 'trackName': 'Trailwise'},
]})


def test_search_returns_the_ordered_results(conn, monkeypatch):
    fake_get(monkeypatch, SEARCH_BODY)
    results = store_api.search(conn, 'hiking maps')
    assert [a['trackId'] for a in results] == [111, 222]


def test_rank_of_counts_from_one():
    results = json.loads(SEARCH_BODY)['results']
    assert store_api.rank_of(results, 222) == 2
    assert store_api.rank_of(results, 999) is None


def test_the_second_call_uses_the_cache(conn, monkeypatch):
    calls = []
    fake_get(monkeypatch, SEARCH_BODY, calls)
    store_api.search(conn, 'hiking maps')
    store_api.search(conn, 'hiking maps')
    assert len(calls) == 1


def test_fresh_bypasses_the_cache(conn, monkeypatch):
    calls = []
    fake_get(monkeypatch, SEARCH_BODY, calls)
    store_api.search(conn, 'hiking maps')
    store_api.search(conn, 'hiking maps', ttl_hours=0)
    assert len(calls) == 2


def test_the_country_belongs_to_the_cache_key(conn, monkeypatch):
    calls = []
    fake_get(monkeypatch, SEARCH_BODY, calls)
    store_api.search(conn, 'hiking maps', country='us')
    store_api.search(conn, 'hiking maps', country='gb')
    assert len(calls) == 2


def test_search_reports_an_answer_that_is_not_json(conn, monkeypatch):
    fake_get(monkeypatch, '<html>error</html>')
    with pytest.raises(store_api.StoreAPIError):
        store_api.search(conn, 'hiking maps')


def test_lookup_by_bundle_identifier(conn, monkeypatch):
    calls = []
    fake_get(monkeypatch, json.dumps({'results': [{'trackId': 5, 'trackName': 'A'}]}), calls)
    assert store_api.lookup(conn, bundle_id='com.example.a')[0]['trackId'] == 5
    assert 'bundleId=com.example.a' in calls[0][0]


def test_hints_read_the_property_list_and_send_the_storefront(conn, monkeypatch):
    body = plistlib.dumps({'hints': [{'term': 'hiking maps'}, {'term': 'hiking gps'}]})
    calls = []
    fake_get(monkeypatch, body.decode('utf-8'), calls)
    assert store_api.hints(conn, 'hiking', country='gb') == ['hiking maps', 'hiking gps']
    assert calls[0][1]['X-Apple-Store-Front'].startswith('143444')


def test_hints_of_an_unknown_country(conn):
    with pytest.raises(store_api.StoreAPIError, match='storefront identifier'):
        store_api.hints(conn, 'hiking', country='zz')


def test_hints_with_a_broken_answer(conn, monkeypatch):
    fake_get(monkeypatch, 'not a plist')
    with pytest.raises(store_api.StoreAPIError, match='property list'):
        store_api.hints(conn, 'hiking')


REVIEW_PAGE = json.dumps({'feed': {'entry': [
    {'title': {'label': 'The app itself'}},                     # no rating: skipped
    {'im:rating': {'label': '5'}, 'title': {'label': 'Great'},
     'content': {'label': 'Offline maps work'}, 'im:version': {'label': '2.1'},
     'updated': {'label': '2026-07-20T10:00:00-07:00'},
     'author': {'name': {'label': 'hiker'}}},
]}})


def test_reviews_are_parsed_and_stop_at_an_empty_page(conn, monkeypatch):
    def body(url, _headers):
        return REVIEW_PAGE if 'page=1' in url else json.dumps({'feed': {}})
    fake_get(monkeypatch, body)
    found = store_api.reviews(conn, 222, pages=3)
    assert len(found) == 1
    assert found[0]['rating'] == 5
    assert found[0]['date'] == '2026-07-20'
    assert found[0]['country'] == 'us'


def test_reviews_of_a_storefront_that_answers_an_error(conn, monkeypatch):
    def body(_url, _headers):
        raise store_api.StoreAPIError('404')
    monkeypatch.setattr(store_api, '_get', body)
    assert store_api.reviews(conn, 222, country='hr') == []
