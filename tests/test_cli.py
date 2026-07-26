"""End-to-end tests of the command line. No test reaches the network."""

import json

import pytest

from aso_advisor import cli, scaffold
from conftest import EXAMPLE, png_bytes, write_workspace

TITLES = """\
locales:
  en-US:
    language: English
    name: 'Trailwise: Hike GPS'
    subtitle: Offline Maps and Routes
    keywords: gps,compass,elevation
"""

TITLES_NEXT = """\
locales:
  en-US:
    language: English
    name: 'Trailwise: Hike GPS'
    subtitle: Offline Maps and Routes
    keywords: gps,compass,elevation,waypoint
"""

BROKEN = """\
locales:
  en-US:
    language: English
    name: This name is much too long for the App Store limit
    subtitle: Offline Maps
    keywords: gps
"""


def run(args, workspace=None):
    argv = list(args)
    if workspace is not None:
        argv = ['--workspace', str(workspace), *argv]
    return cli.main(argv)


@pytest.fixture
def ws(tmp_path):
    return write_workspace(tmp_path / 'aso', versions={'1.0': {'titles.yaml': TITLES}})


# -- init ---------------------------------------------------------------------

def test_init_writes_a_complete_workspace(tmp_path, capsys):
    assert run(['init', '--path', str(tmp_path / 'aso'), '--metadata-version', '1.0']) == 0
    root = tmp_path / 'aso'
    for name in ('aso.yaml', 'strategy.yaml', 'README.md', '.gitignore'):
        assert (root / name).is_file()
    assert (root / 'versions' / '1.0' / 'titles_and_keywords.yaml').is_file()
    assert (root / 'versions' / '1.0' / 'descriptions.yaml').is_file()
    assert 'Next steps' in capsys.readouterr().out


def test_init_refuses_to_overwrite(tmp_path):
    run(['init', '--path', str(tmp_path / 'aso')])
    assert run(['init', '--path', str(tmp_path / 'aso')]) == cli.EXIT_ERROR
    assert run(['init', '--path', str(tmp_path / 'aso'), '--force']) == 0


def test_a_new_workspace_can_be_audited(tmp_path):
    run(['init', '--path', str(tmp_path / 'aso'), '--metadata-version', '1.0'])
    assert run(['audit', '--no-report'], workspace=tmp_path / 'aso') == 0


def test_init_uses_the_public_data_when_it_can(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scaffold, 'fetch_identity', lambda **_kwargs: {
        'track_id': 42, 'bundle_id': 'com.example.trailwise', 'name': 'Trailwise',
        'description': 'An offline hike tracker.', 'version': '2.1', 'seller': 'Example',
        'url': 'https://apps.apple.com/app/id42'})
    run(['init', '--path', str(tmp_path / 'aso'), '--app-id', '42'])
    config = (tmp_path / 'aso' / 'aso.yaml').read_text(encoding='utf-8')
    assert 'track_id: 42' in config
    assert 'name: Trailwise' in config
    assert 'Found: Trailwise' in capsys.readouterr().out


@pytest.mark.parametrize('value, expected', [
    ('123456789', 123456789),
    ('https://apps.apple.com/us/app/trailwise/id987654321?mt=8', 987654321),
    ('not an id', 0),
    ('', 0),
])
def test_parse_app_id(value, expected):
    assert scaffold.parse_app_id(value) == expected


# -- audit --------------------------------------------------------------------

def test_audit_writes_a_report_with_a_timestamp(ws):
    assert run(['audit'], workspace=ws) == 0
    reports = list((ws / 'reports').glob('aso-report-*.md'))
    assert len(reports) == 1
    assert reports[0].stem.split('-')[-1].isdigit()


def test_audit_json_output(ws, capsys):
    run(['audit', '--json', '--no-report'], workspace=ws)
    data = json.loads(capsys.readouterr().out)
    assert data['metadata_version'] == '1.0'
    assert isinstance(data['suggestions'], list)


def test_audit_fail_on_returns_the_pipeline_code(tmp_path):
    workspace = write_workspace(tmp_path / 'aso', versions={'1.0': {'titles.yaml': BROKEN}})
    assert run(['audit', '--no-report', '--no-state'], workspace=workspace) == 0
    assert run(['audit', '--no-report', '--no-state', '--fail-on', 'critical'],
               workspace=workspace) == cli.EXIT_FINDINGS


def test_fail_on_ignores_a_severity_below_the_threshold(ws):
    assert run(['audit', '--no-report', '--no-state', '--fail-on', 'critical'],
               workspace=ws) == 0


def test_no_state_writes_no_database(ws):
    run(['audit', '--no-report', '--no-state'], workspace=ws)
    assert not (ws / 'state').exists()


def test_audit_selects_an_older_version(tmp_path, capsys):
    workspace = write_workspace(tmp_path / 'aso', versions={
        '1.0': {'titles.yaml': TITLES}, '1.1': {'titles.yaml': TITLES_NEXT}})
    run(['audit', '--no-report', '--no-state', '--metadata-version', '1.0'],
        workspace=workspace)
    assert 'metadata 1.0' in capsys.readouterr().out


def test_audit_of_an_unknown_version_explains_the_choices(ws, capsys):
    assert run(['audit', '--metadata-version', '9.9'], workspace=ws) == cli.EXIT_ERROR
    assert 'Available: 1.0' in capsys.readouterr().err


def test_audit_without_a_workspace(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ASO_WORKSPACE', raising=False)
    assert cli.main(['audit']) == cli.EXIT_ERROR
    assert 'aso init' in capsys.readouterr().err


def test_no_subcommand_means_audit(ws, capsys):
    assert cli.main(['--workspace', str(ws)]) == 0
    assert 'ASO ADVISOR' in capsys.readouterr().out


# -- the lifecycle of a suggestion --------------------------------------------

def test_list_show_dismiss_and_reopen(ws, capsys):
    run(['audit', '--no-report'], workspace=ws)
    capsys.readouterr()                      # Drop the output of the audit.
    run(['list'], workspace=ws)
    printed = capsys.readouterr().out
    fid = printed.split('\n')[0].split()[0]
    assert fid.startswith('S-')

    assert run(['show', fid], workspace=ws) == 0
    assert fid in capsys.readouterr().out

    assert run(['dismiss', fid, 'a deliberate bet'], workspace=ws) == 0
    capsys.readouterr()
    run(['list'], workspace=ws)
    assert fid not in capsys.readouterr().out

    run(['list', '--all'], workspace=ws)
    assert 'dismissed' in capsys.readouterr().out

    assert run(['reopen', fid], workspace=ws) == 0
    capsys.readouterr()
    run(['list'], workspace=ws)
    assert fid in capsys.readouterr().out


def test_show_of_an_unknown_identifier(ws):
    run(['audit', '--no-report'], workspace=ws)
    assert run(['show', 'S-00000000'], workspace=ws) == cli.EXIT_ERROR


def test_list_filters_by_severity(ws, capsys):
    run(['audit', '--no-report'], workspace=ws)
    run(['list', '--severity', 'critical'], workspace=ws)
    assert 'Nothing to show' in capsys.readouterr().out


def test_list_as_json(ws, capsys):
    run(['audit', '--no-report'], workspace=ws)
    capsys.readouterr()
    run(['list', '--json'], workspace=ws)
    assert isinstance(json.loads(capsys.readouterr().out), list)


def test_history_shows_each_run(ws, capsys):
    run(['audit', '--no-report'], workspace=ws)
    run(['audit', '--no-report'], workspace=ws)
    run(['history'], workspace=ws)
    printed = capsys.readouterr().out
    assert printed.count('1.0') >= 2


# -- versions, diff, assets, rules, where -------------------------------------

def test_versions_lists_every_directory(tmp_path, capsys):
    workspace = write_workspace(tmp_path / 'aso', versions={
        '1.0': {'titles.yaml': TITLES}, '1.1': {'titles.yaml': TITLES_NEXT}})
    run(['versions'], workspace=workspace)
    printed = capsys.readouterr().out
    assert '1.0' in printed and '1.1' in printed and '(newest)' in printed


def test_diff_between_two_versions(tmp_path, capsys):
    workspace = write_workspace(tmp_path / 'aso', versions={
        '1.0': {'titles.yaml': TITLES}, '1.1': {'titles.yaml': TITLES_NEXT}})
    run(['diff'], workspace=workspace)
    printed = capsys.readouterr().out
    assert '1.0 → 1.1' in printed
    assert '+waypoint' in printed


def test_diff_of_the_first_version(ws, capsys):
    run(['diff'], workspace=ws)
    assert 'Two versions are necessary' in capsys.readouterr().out


def test_assets_command_reports_the_tree_and_the_problems(ws, capsys):
    device = ws / 'versions' / '1.0' / 'assets' / 'en-US' / 'screenshots' / 'iphone-6.9'
    device.mkdir(parents=True)
    (device / '01-hero.png').write_bytes(png_bytes(1242, 2688))
    run(['assets'], workspace=ws)
    printed = capsys.readouterr().out
    assert 'iphone-6.9' in printed
    assert 'unexpected size' in printed


def test_assets_command_without_assets(ws, capsys):
    run(['assets'], workspace=ws)
    assert 'No asset in' in capsys.readouterr().out


def test_rules_command_lists_the_identifiers(capsys):
    assert cli.main(['rules']) == 0
    printed = capsys.readouterr().out
    assert 'DUP_XLOC' in printed and 'ASSET_SIZE' in printed


def test_where_shows_the_paths(ws, capsys):
    run(['where'], workspace=ws)
    printed = capsys.readouterr().out
    assert 'workspace' in printed and str(ws) in printed


def test_disabled_rules_are_not_reported(tmp_path, capsys):
    config = """\
version: 1
app:
  primary_locale: en-US
audit:
  disable_rules: [LIMIT, BUDGET, EMPTY]
"""
    workspace = write_workspace(tmp_path / 'aso', config=config,
                                versions={'1.0': {'titles.yaml': BROKEN}})
    run(['audit', '--no-report', '--no-state'], workspace=workspace)
    assert 'CRITICAL:0' in capsys.readouterr().out


# -- live commands without a network ------------------------------------------

def test_a_live_command_needs_the_app_identifier(tmp_path, capsys):
    workspace = write_workspace(tmp_path / 'aso', config='version: 1\n',
                                versions={'1.0': {'titles.yaml': TITLES}})
    assert run(['rank'], workspace=workspace) == cli.EXIT_ERROR
    assert 'track_id' in capsys.readouterr().err


def test_cache_command(ws, capsys):
    run(['audit', '--no-report'], workspace=ws)
    capsys.readouterr()
    run(['cache'], workspace=ws)
    assert 'cached answer' in capsys.readouterr().out
    run(['cache', '--clear'], workspace=ws)
    assert 'removed' in capsys.readouterr().out


# -- the example workspace ----------------------------------------------------

def test_the_example_workspace_audits_cleanly(capsys):
    assert run(['audit', '--no-report', '--no-state'], workspace=EXAMPLE) == 0
    printed = capsys.readouterr().out
    assert 'metadata 2.1' in printed
    assert 'CRITICAL:0' in printed


def test_the_example_workspace_teaches_the_phrase_rule(capsys):
    run(['audit', '--no-report', '--no-state', '--json'], workspace=EXAMPLE)
    data = json.loads(capsys.readouterr().out)
    phrases = [s for s in data['suggestions'] if s['rule'] == 'PHRASE']
    assert any('offline hiking maps' in s['title'] for s in phrases)


# -- App Store Connect commands (no network) ----------------------------------

def test_auth_without_credentials_explains_how_to_make_a_key(ws, capsys, monkeypatch):
    from aso_advisor.asc import client as asc

    for name in (asc.ENV_KEY_ID, asc.ENV_ISSUER_ID, asc.ENV_KEY_PATH,
                 asc.ENV_KEY_VALUE, asc.ENV_APP_ID):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(ws)
    assert run(['auth'], workspace=ws) == cli.EXIT_ERROR
    printed = capsys.readouterr().err
    assert 'APP_STORE_CONNECT_KEY_ID' in printed
    assert 'Users and Access' in printed


def test_auth_shows_the_resolved_credentials(ws, capsys, monkeypatch):
    from aso_advisor.asc import client as asc

    key = ws / 'AuthKey_TEST.p8'
    key.write_text('-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----\n')
    monkeypatch.setenv(asc.ENV_KEY_ID, 'KEY123')
    monkeypatch.setenv(asc.ENV_ISSUER_ID, 'ISSUER')
    monkeypatch.setenv(asc.ENV_KEY_PATH, str(key))
    monkeypatch.setenv(asc.ENV_APP_ID, '4242')
    assert run(['auth'], workspace=ws) == 0
    printed = capsys.readouterr().out
    assert 'KEY123' in printed and '4242' in printed
    assert 'BEGIN PRIVATE KEY' not in printed        # never print the key itself


def test_push_stops_on_a_critical_finding(tmp_path, capsys, monkeypatch):
    from aso_advisor.asc import push as push_module

    workspace_dir = write_workspace(tmp_path / 'aso',
                                    versions={'1.0': {'titles.yaml': BROKEN}})
    monkeypatch.setattr(push_module, 'cmd_push',
                        lambda *a, **k: pytest.fail('the push must not start'))
    assert run(['push'], workspace=workspace_dir) == cli.EXIT_FINDINGS
    assert 'App Store Connect will refuse' in capsys.readouterr().err


def test_push_with_skip_audit_goes_on(tmp_path, monkeypatch):
    from aso_advisor.asc import push as push_module

    workspace_dir = write_workspace(tmp_path / 'aso',
                                    versions={'1.0': {'titles.yaml': BROKEN}})
    seen = {}

    def fake_push(ws, locales, **kwargs):
        seen['locales'] = locales
        seen['dry_run'] = kwargs.get('dry_run')
        return 0

    monkeypatch.setattr(push_module, 'cmd_push', fake_push)
    assert run(['push', '--skip-audit', '--dry-run'], workspace=workspace_dir) == 0
    assert 'en-US' in seen['locales']
    assert seen['dry_run'] is True


def test_pull_passes_the_options(ws, monkeypatch):
    from aso_advisor.asc import pull as pull_module

    seen = {}

    def fake_pull(workspace_arg, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(pull_module, 'cmd_pull', fake_pull)
    assert run(['pull', '--editable', '--locale', 'de-DE'], workspace=ws) == 0
    assert seen['from_editable'] is True
    assert seen['locale'] == 'de-DE'


def test_push_assets_reads_the_version_directory(ws, monkeypatch, capsys):
    from aso_advisor.asc import media as media_module

    seen = {}

    def fake_push_assets(workspace_arg, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(media_module, 'cmd_push_assets', fake_push_assets)
    assert run(['push-assets', '--dry-run'], workspace=ws) == 0
    assert seen['assets_dir'] == ws / 'versions' / '1.0' / 'assets'
    assert seen['dry_run'] is True
    assert 'Reading the assets' in capsys.readouterr().out


def test_phrases_prints_and_writes(ws, capsys, monkeypatch):
    from aso_advisor import store_api

    monkeypatch.setattr(store_api, 'hints', lambda _conn, term, **k:
                        ['hike tracker with maps', 'trail gps'] if term else [])
    monkeypatch.setattr(store_api, 'lookup', lambda *a, **k: [])
    (ws / 'strategy.yaml').write_text('discovery_seeds: [hiking]\n', encoding='utf-8')
    assert run(['phrases', '--write'], workspace=ws) == 0
    printed = capsys.readouterr().out
    assert 'Proposed target phrases' in printed
    assert 'trail gps' in printed
    text = (ws / 'strategy.yaml').read_text(encoding='utf-8')
    assert 'phrase_targets:' in text
    assert 'trail gps' in text
