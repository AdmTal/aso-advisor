import pytest

from aso_advisor import db
from aso_advisor.model import LocaleMeta, Suggestion


@pytest.fixture
def conn():
    connection = db.connect_memory()
    yield connection
    connection.close()


def suggestion(key='gps', rule='DUP_TITLE', severity='HIGH'):
    return Suggestion(rule, key, 'en-US', severity, f'{key} is a problem',
                      detail='why', fix='how')


def run(conn, findings, version='1.0'):
    run_id = db.start_run(conn, version)
    return run_id, db.reconcile(conn, run_id, findings)


def test_first_run_marks_everything_new(conn):
    found = [suggestion('gps'), suggestion('map')]
    _run_id, stats = run(conn, found)
    assert stats['new'] == 2
    assert stats['open'] == 2
    assert all(s.is_new for s in found)


def test_second_run_keeps_the_same_identifier(conn):
    run(conn, [suggestion('gps')])
    again = [suggestion('gps')]
    _run_id, stats = run(conn, again)
    assert stats['new'] == 0
    assert not again[0].is_new
    assert again[0].status == 'open'


def test_a_problem_that_disappears_is_resolved(conn):
    run(conn, [suggestion('gps'), suggestion('map')])
    _run_id, stats = run(conn, [suggestion('gps')])
    assert [r['title'] for r in stats['resolved']] == ['map is a problem']
    assert db.get_suggestion(conn, suggestion('map').fid)['status'] == 'resolved'


def test_a_problem_that_comes_back_is_a_regression(conn):
    run(conn, [suggestion('gps')])
    run(conn, [])
    again = [suggestion('gps')]
    _run_id, stats = run(conn, again)
    assert stats['regressed'] == 1
    assert again[0].regressed


def test_a_dismissed_problem_stays_dismissed(conn):
    found = [suggestion('gps')]
    run(conn, found)
    db.set_status(conn, found[0].fid, 'dismissed', 'a deliberate bet')
    later = [suggestion('gps')]
    run(conn, later)
    assert later[0].status == 'dismissed'
    assert db.get_suggestion(conn, later[0].fid)['note'] == 'a deliberate bet'


def test_reopen_makes_it_visible_again(conn):
    found = [suggestion('gps')]
    run(conn, found)
    db.set_status(conn, found[0].fid, 'dismissed')
    db.set_status(conn, found[0].fid, 'open')
    later = [suggestion('gps')]
    run(conn, later)
    assert later[0].status == 'open'


def test_set_status_of_an_unknown_identifier(conn):
    assert db.set_status(conn, 'S-nothing', 'dismissed') is False


def test_the_text_of_a_suggestion_may_change(conn):
    run(conn, [suggestion('gps')])
    changed = Suggestion('DUP_TITLE', 'gps', 'en-US', 'MEDIUM', 'a new wording')
    run(conn, [changed])
    row = db.get_suggestion(conn, changed.fid)
    assert row['title'] == 'a new wording'
    assert row['severity'] == 'MEDIUM'


def test_list_suggestions_filters_by_status(conn):
    found = [suggestion('gps'), suggestion('map')]
    run(conn, found)
    db.set_status(conn, found[0].fid, 'dismissed')
    assert len(db.list_suggestions(conn, 'open')) == 1
    assert len(db.list_suggestions(conn, 'all')) == 2


def test_run_history_is_newest_first(conn):
    run(conn, [suggestion('gps')], version='1.0')
    run(conn, [], version='1.1')
    rows = db.run_history(conn)
    assert [r['version'] for r in rows] == ['1.1', '1.0']
    assert rows[0]['resolved_count'] == 1


def test_snapshots_store_the_indexing_fields(conn):
    run_id = db.start_run(conn, '1.0')
    db.save_snapshots(conn, run_id, '1.0',
                      {'en-US': LocaleMeta(code='en-US', name='A', keywords='gps')})
    rows = conn.execute('SELECT field, value FROM snapshots ORDER BY field').fetchall()
    assert [(r['field'], r['value']) for r in rows] == [
        ('keywords', 'gps'), ('name', 'A'), ('subtitle', '')]


# -- live-data tables ---------------------------------------------------------

def test_cache_returns_a_fresh_answer_and_drops_an_old_one(conn):
    db.cache_put(conn, 'https://example.test/a', 'body')
    assert db.cache_get(conn, 'https://example.test/a', 12) == 'body'
    assert db.cache_get(conn, 'https://example.test/a', 0) is None
    assert db.cache_get(conn, 'https://example.test/missing', 12) is None


def test_cache_clear(conn):
    db.cache_put(conn, 'https://example.test/a', 'body')
    assert db.cache_clear(conn) == 1
    assert db.cache_get(conn, 'https://example.test/a', 12) is None


def test_rank_history_and_summary(conn):
    db.record_rank(conn, 'hiking maps', 'us', 40, 200, [[1, 'Rival']])
    db.record_rank(conn, 'hiking maps', 'us', 12, 200, [[1, 'Rival']])
    rows = db.rank_summary(conn)
    assert rows[0]['rank'] == 12
    assert rows[0]['prev'] == 40


def test_competitor_snapshots_keep_the_previous_row(conn):
    snap = {'track_id': 7, 'country': 'us', 'name': 'Rival', 'version': '1.0',
            'released': '2026-01-01', 'rating': 4.5, 'rating_count': 100, 'price': 0.0,
            'desc_hash': 'aaa'}
    baseline = db.last_competitor_id(conn)
    db.record_competitor(conn, snap)
    assert db.previous_competitor(conn, 7, 'us', baseline + 1) is None
    baseline = db.last_competitor_id(conn)
    db.record_competitor(conn, {**snap, 'name': 'Rival Pro', 'rating_count': 150})
    previous = db.previous_competitor(conn, 7, 'us', baseline + 1)
    assert previous['name'] == 'Rival'


def test_connect_makes_the_parent_directory(tmp_path):
    path = tmp_path / 'deep' / 'state' / 'aso.sqlite3'
    connection = db.connect(path)
    connection.close()
    assert path.exists()
