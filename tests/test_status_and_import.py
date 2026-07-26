"""Tests for `aso status` and `aso import`."""

import pytest

from aso_advisor import db, importers, loader, status, workspace
from conftest import write_workspace

VERSION = """\
locales:
  en-US:
    language: English
    name: Trailwise
    subtitle: Offline Maps
    keywords: gps,compass
"""


@pytest.fixture
def ws(tmp_path):
    root = write_workspace(tmp_path / 'aso', versions={'1.0': {'titles.yaml': VERSION}})
    return workspace.load(explicit=str(root))


def text_of(lines):
    return '\n'.join(str(line) for line in lines)


# -- status -------------------------------------------------------------------

def test_status_shows_the_basics(ws):
    out = text_of(status.collect(ws))
    assert str(ws.root) in out
    assert 'Test App' in out
    assert '1.0 (newest of 1)' in out
    assert '1 locale(s)' in out


def test_status_without_a_version(tmp_path):
    root = write_workspace(tmp_path / 'aso')
    out = text_of(status.collect(workspace.load(explicit=str(root))))
    assert 'no version yet' in out


def test_status_says_that_the_sync_state_is_unknown(ws):
    assert 'unknown' in text_of(status.collect(ws))


def test_status_counts_the_work_that_nobody_pushed(ws):
    conn = db.connect(ws.db_path)
    db.save_sync_snapshot(conn, '1.0', {'en-US': {'name': 'Trailwise',
                                                  'subtitle': 'Offline Maps',
                                                  'keywords': 'gps'}}, 'pull')
    conn.close()
    out = text_of(status.collect(ws))
    assert '1 field(s) in 1 locale(s) changed' in out
    assert 'en-US keywords' in out


def test_status_says_when_nothing_is_unpushed(ws):
    conn = db.connect(ws.db_path)
    db.save_sync_snapshot(conn, '1.0', loader.load_version_raw(ws.versions_dir / '1.0'),
                          'push')
    conn.close()
    assert 'nothing — the workspace matches the last push' in text_of(status.collect(ws))


def test_status_shows_the_audit_and_the_ranks(ws):
    from aso_advisor.model import Suggestion

    conn = db.connect(ws.db_path)
    run_id = db.start_run(conn, '1.0')
    db.reconcile(conn, run_id, [Suggestion('EMPTY', 'k', 'en-US', 'HIGH', 'a problem')])
    db.record_rank(conn, 'hiking maps', 'us', 40, 200, [])
    db.record_rank(conn, 'hiking maps', 'us', 12, 200, [])
    conn.close()
    out = text_of(status.collect(ws))
    assert 'run #1' in out and '1 open' in out and 'high:1' in out
    assert '1 term(s)' in out
    assert '▲ +28' in out and 'hiking maps' in out


def test_status_names_the_next_steps(ws):
    out = text_of(status.collect(ws))
    assert 'next:' in out
    assert 'aso audit' in out            # the strategy is complete enough


def test_status_points_at_the_phrase_generator_when_targets_are_missing(tmp_path):
    root = write_workspace(tmp_path / 'aso', strategy='brand_phrases: [x]\n',
                           versions={'1.0': {'titles.yaml': VERSION}})
    out = text_of(status.collect(workspace.load(explicit=str(root))))
    assert 'aso phrases' in out


def test_status_reports_a_missing_key(ws, monkeypatch):
    from aso_advisor.asc import client as asc

    for name in (asc.ENV_KEY_ID, asc.ENV_ISSUER_ID, asc.ENV_KEY_PATH,
                 asc.ENV_KEY_VALUE, asc.ENV_APP_ID):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(ws.root)
    assert 'aso auth' in text_of(status.collect(ws))


def test_status_online_reports_the_drift(ws):
    class FakeClient:
        pass

    def fake_collect(_client, quiet=False):
        return '1.0', {'en-US': {'name': 'Changed in the web interface',
                                 'subtitle': 'Offline Maps', 'keywords': 'gps,compass'}}

    import aso_advisor.asc.pull as pull_module
    original = pull_module.collect
    pull_module.collect = fake_collect
    try:
        out = text_of(status.collect(ws, online=True, client=FakeClient()))
    finally:
        pull_module.collect = original
    assert 'live version 1.0' in out
    assert 'differ from the store' in out


# -- import -------------------------------------------------------------------

def fastlane_tree(root):
    """A small but realistic fastlane deliver tree."""
    for locale, fields in {
        'en-US': {'name': 'Trailwise', 'subtitle': 'Offline Maps',
                  'keywords': 'gps,compass', 'description': 'What the app does.',
                  'release_notes': 'Faster maps.', 'support_url': 'https://example.test'},
        'de-DE': {'name': 'Trailwise DE', 'keywords': 'karte,berg'},
    }.items():
        directory = root / locale
        directory.mkdir(parents=True)
        for field, value in fields.items():
            (directory / f'{field}.txt').write_text(value + '\n', encoding='utf-8')
    (root / 'default').mkdir()
    (root / 'default' / 'privacy_url.txt').write_text('https://example.test/privacy')
    (root / 'review_information').mkdir()
    (root / 'review_information' / 'first_name.txt').write_text('Ada')
    (root / 'copyright.txt').write_text('2026 Example')
    return root


def test_read_a_fastlane_tree(tmp_path):
    locales, notes = importers.read_fastlane(fastlane_tree(tmp_path / 'metadata'))
    assert sorted(locales) == ['de-DE', 'en-US']
    assert locales['en-US']['name'] == 'Trailwise'
    assert locales['en-US']['whats_new'] == 'Faster maps.'     # release_notes
    assert locales['en-US']['support_url'] == 'https://example.test'
    assert 'default' in ' '.join(notes)


def test_the_default_directory_fills_the_gaps(tmp_path):
    locales, _notes = importers.read_fastlane(fastlane_tree(tmp_path / 'metadata'))
    assert locales['de-DE']['privacy_policy_url'] == 'https://example.test/privacy'
    assert locales['en-US']['privacy_policy_url'] == 'https://example.test/privacy'


def test_the_directories_that_are_not_locales_are_skipped(tmp_path):
    locales, _notes = importers.read_fastlane(fastlane_tree(tmp_path / 'metadata'))
    assert 'review_information' not in locales
    assert 'default' not in locales


def test_screenshots_are_reported_but_not_moved(tmp_path):
    root = fastlane_tree(tmp_path / 'metadata')
    shots = tmp_path / 'screenshots' / 'en-US'
    shots.mkdir(parents=True)
    (shots / '01.png').write_bytes(b'x')
    _locales, notes = importers.read_fastlane(root)
    assert any('screenshot' in note for note in notes)


def test_a_directory_that_does_not_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        importers.read_fastlane(tmp_path / 'nothing')


def test_import_writes_a_version(tmp_path, capsys):
    root = write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(root))
    tree = fastlane_tree(tmp_path / 'fastlane' / 'metadata')
    assert importers.cmd_import(ws, tree, version='1.0') == 0
    written = loader.load_version_raw(ws.versions_dir / '1.0')
    assert written['en-US']['keywords'] == 'gps,compass'
    assert 'note:' in capsys.readouterr().out


def test_import_does_not_overwrite_without_force(tmp_path):
    root = write_workspace(tmp_path / 'aso', versions={'1.0': {'titles.yaml': VERSION}})
    ws = workspace.load(explicit=str(root))
    tree = fastlane_tree(tmp_path / 'fastlane' / 'metadata')
    assert importers.cmd_import(ws, tree, version='1.0') == 1
    assert importers.cmd_import(ws, tree, version='1.0', force=True) == 0


def test_import_of_an_empty_tree(tmp_path):
    root = write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(root))
    empty = tmp_path / 'metadata'
    empty.mkdir()
    assert importers.cmd_import(ws, empty) == 1
