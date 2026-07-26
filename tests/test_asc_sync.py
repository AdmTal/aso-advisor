"""Tests for pull, push, and push-assets, against a fake App Store Connect."""

import pytest

from aso_advisor import loader, workspace
from aso_advisor.asc import client as asc
from aso_advisor.asc import media, pull, push
from conftest import png_bytes, write_workspace


class FakeClient:
    """A stand-in for ASCClient that answers from a script and records calls."""

    def __init__(self, routes=None, collections=None):
        self.creds = asc.Credentials(key_id='A', issuer_id='B', private_key='k',
                                     app_id='123')
        self.routes = routes or {}
        self.collections = collections or {}
        self.calls = []
        self.uploads = []

    def request(self, method, path, params=None, json_body=None):
        self.calls.append((method, path, json_body))
        for (route_method, route_path), answer in self.routes.items():
            if route_method == method and route_path == path:
                return answer(json_body) if callable(answer) else answer
        return {}

    def get_all(self, path, params=None):
        self.calls.append(('GET', path, None))
        return self.collections.get(path, [])

    def upload_chunk(self, operation, data):
        self.uploads.append((operation['url'], len(data)))
        return 200


VERSION = {'id': 'v1', 'attributes': {'versionString': '2.1',
                                      'appStoreState': 'PREPARE_FOR_SUBMISSION'}}
APP_INFO = {'id': 'i1', 'attributes': {'appStoreState': 'PREPARE_FOR_SUBMISSION'}}


def base_collections(version_locales=(), info_locales=()):
    return {
        '/v1/apps/123/appStoreVersions': [VERSION],
        '/v1/apps/123/appInfos': [APP_INFO],
        '/v1/appStoreVersions/v1/appStoreVersionLocalizations': list(version_locales),
        '/v1/appInfos/i1/appInfoLocalizations': list(info_locales),
    }


def localization(locale, ident, **attributes):
    return {'id': ident, 'attributes': {'locale': locale, **attributes}}


@pytest.fixture
def ws(tmp_path):
    root = write_workspace(tmp_path / 'aso', versions={'2.1': {'titles.yaml': """\
locales:
  en-US:
    language: English
    name: Trailwise
    subtitle: Offline Maps
    keywords: gps,compass
    description: What the app does.
    support_url: https://example.test/support
"""}})
    return workspace.load(explicit=str(root))


# -- pull ---------------------------------------------------------------------

def test_pull_writes_the_live_metadata(ws, capsys):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', description='Live description',
                                      keywords='gps,map', promotionalText='Try it')],
        info_locales=[localization('en-US', 'a1', name='Trailwise Live',
                                   subtitle='Live subtitle')]))
    client.collections['/v1/apps/123/appStoreVersions'] = [
        {'id': 'v1', 'attributes': {'versionString': '3.0',
                                    'appStoreState': 'READY_FOR_SALE'}}]
    client.collections['/v1/apps/123/appInfos'] = [
        {'id': 'i1', 'attributes': {'appStoreState': 'READY_FOR_SALE'}}]

    assert pull.cmd_pull(ws, client=client) == 0
    written = loader.load_version_raw(ws.versions_dir / '3.0')
    assert written['en-US']['name'] == 'Trailwise Live'
    assert written['en-US']['keywords'] == 'gps,map'
    assert written['en-US']['promotional_text'] == 'Try it'
    assert 'written into' in capsys.readouterr().out


def test_pull_into_a_named_version(ws):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='gps')],
        info_locales=[localization('en-US', 'a1', name='Name')]))
    pull.cmd_pull(ws, version='9.9', from_editable=True, client=client)
    assert (ws.versions_dir / '9.9').is_dir()


def test_pull_keeps_the_notes_of_the_existing_directory(ws):
    target = ws.versions_dir / '2.1'
    (target / 'titles.yaml').write_text("""\
locales:
  de-DE:
    language: German
    name: Alter Name
    name_eng: Old name
""", encoding='utf-8')
    client = FakeClient(collections=base_collections(
        version_locales=[localization('de-DE', 'l1', keywords='karte')],
        info_locales=[localization('de-DE', 'a1', name='Neuer Name')]))
    pull.cmd_pull(ws, version='2.1', from_editable=True, force=True, client=client)
    text = (target / 'titles.yaml').read_text(encoding='utf-8')
    assert 'language: German' in text
    assert 'name_eng: Old name' in text
    assert 'Neuer Name' in text


def test_pull_of_one_unknown_locale(ws):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1')]))
    with pytest.raises(SystemExit, match='fr-FR'):
        pull.cmd_pull(ws, from_editable=True, locale='fr-FR', client=client)


# -- push ---------------------------------------------------------------------

def test_push_updates_an_existing_locale(ws):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1')],
        info_locales=[localization('en-US', 'a1')]))
    locales = loader.load_version_raw(ws.versions_dir / '2.1')
    assert push.cmd_push(ws, locales, client=client) == 0
    patched = {(method, path) for method, path, _body in client.calls
               if method == 'PATCH'}
    assert ('PATCH', '/v1/appStoreVersionLocalizations/l1') in patched
    assert ('PATCH', '/v1/appInfoLocalizations/a1') in patched


def test_push_sends_the_right_attribute_names(ws):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1')],
        info_locales=[localization('en-US', 'a1')]))
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'), client=client)
    version_body = next(body for method, path, body in client.calls
                        if path == '/v1/appStoreVersionLocalizations/l1')
    attributes = version_body['data']['attributes']
    assert attributes['keywords'] == 'gps,compass'
    assert attributes['supportUrl'] == 'https://example.test/support'
    info_body = next(body for method, path, body in client.calls
                     if path == '/v1/appInfoLocalizations/a1')
    assert info_body['data']['attributes']['name'] == 'Trailwise'
    assert 'keywords' not in info_body['data']['attributes']


def test_push_creates_a_locale_that_the_store_does_not_have(ws):
    client = FakeClient(routes={('POST', '/v1/appStoreVersionLocalizations'):
                                {'data': {'id': 'new'}},
                                ('POST', '/v1/appInfoLocalizations'):
                                {'data': {'id': 'new'}}},
                        collections=base_collections())
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'), client=client)
    created = [body for method, path, body in client.calls if method == 'POST']
    assert created[0]['data']['attributes']['locale'] == 'en-US'
    assert created[0]['data']['relationships']['appStoreVersion']['data']['id'] == 'v1'


def test_push_dry_run_sends_nothing(ws, capsys):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1')],
        info_locales=[localization('en-US', 'a1')]))
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'), dry_run=True,
                  client=client)
    assert not [c for c in client.calls if c[0] in ('PATCH', 'POST', 'DELETE')]
    assert 'dry run' in capsys.readouterr().out


def test_push_stops_when_a_field_is_too_long(ws, capsys):
    locales = {'en-US': {'name': 'x' * 40}}
    assert push.cmd_push(ws, locales, client=FakeClient()) == 2
    assert 'en-US.name' in capsys.readouterr().err


def test_push_recovers_when_the_store_made_the_locale_itself(ws):
    state = {'created': False}

    def refuse(_body):
        state['created'] = True
        raise asc.ASCError(409, [{'code': 'ENTITY_ERROR.DUPLICATE'}])

    client = FakeClient(routes={('POST', '/v1/appStoreVersionLocalizations'): refuse,
                                ('POST', '/v1/appInfoLocalizations'): {'data': {'id': 'x'}}},
                        collections=base_collections())

    original_get_all = client.get_all

    def get_all(path, params=None):
        if (path == '/v1/appStoreVersions/v1/appStoreVersionLocalizations'
                and state['created']):
            return [localization('en-US', 'auto')]
        return original_get_all(path, params)

    client.get_all = get_all
    assert push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'),
                         client=client) == 0
    assert any(path == '/v1/appStoreVersionLocalizations/auto'
               for _method, path, _body in client.calls)


def test_push_reports_a_locale_that_failed(ws, capsys):
    def fail(_body):
        raise asc.ASCError(422, [{'code': 'ENTITY_ERROR', 'title': 'no'}])

    client = FakeClient(routes={('PATCH', '/v1/appStoreVersionLocalizations/l1'): fail},
                        collections=base_collections(
                            version_locales=[localization('en-US', 'l1')],
                            info_locales=[localization('en-US', 'a1')]))
    assert push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'),
                         client=client) == 1
    assert 'FAILED' in capsys.readouterr().err


# -- media --------------------------------------------------------------------

@pytest.mark.parametrize('name, expected', [
    ('iphone-6.9', 'APP_IPHONE_67'),        # the workspace layout
    ('ipad-13', 'APP_IPAD_PRO_3GEN_129'),
    ('iphone-6.5', 'APP_IPHONE_65'),
    ('phone', 'APP_IPHONE_67'),             # the short names
    ('ipad', 'APP_IPAD_PRO_3GEN_129'),
    ('iOS Phones  6.9', 'APP_IPHONE_67'),   # a label from a design tool
    ('iOS iPad  13', 'APP_IPAD_PRO_3GEN_129'),
    ('iPhone 6.5', 'APP_IPHONE_65'),
    ('notes', None),
])
def test_device_directory_names(name, expected):
    assert media.classify_device_dir(name) == expected


def test_preview_types_come_from_the_display_types():
    assert media.classify_preview_dir('iphone-6.9') == 'IPHONE_67'
    assert media.classify_preview_dir('iPad 13') == 'IPAD_PRO_3GEN_129'


@pytest.mark.parametrize('name, expected', [
    ('English (en-US)', 'en-US'),
    ('en-US', 'en-US'),
    ('Chinese (zh-Hans)', 'zh-Hans'),
    ('zh-Hans', 'zh-Hans'),
    ('previews', None),
])
def test_locale_directory_names(name, expected):
    assert media.locale_of_dir(name) == expected


def shot(root, *parts):
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes(40, 60))
    return path


def test_plan_from_the_workspace_tree(tmp_path):
    shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '02.png')
    shot(tmp_path, 'de-DE', 'screenshots', 'ipad-13', '01.png')
    plan = media.plan_from_workspace(tmp_path, 'screenshots')
    assert sorted(plan) == ['de-DE', 'en-US']
    assert len(plan['en-US']['APP_IPHONE_67']) == 2
    assert 'APP_IPAD_PRO_3GEN_129' in plan['de-DE']


def test_plan_from_the_workspace_tree_with_filters(tmp_path):
    shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'screenshots', 'ipad-13', '01.png')
    shot(tmp_path, 'de-DE', 'screenshots', 'iphone-6.9', '01.png')
    plan = media.plan_from_workspace(tmp_path, 'screenshots', locale='en-US',
                                     device='ipad-13')
    assert list(plan) == ['en-US']
    assert list(plan['en-US']) == ['APP_IPAD_PRO_3GEN_129']


def test_plan_from_an_external_locale_first_tree(tmp_path):
    shot(tmp_path, 'English (en-US)', 'iOS Phones  6.9', '01.png')
    shot(tmp_path, 'German (de-DE)', 'iOS iPad  13', '01.png')
    plan = media.plan_from_tree(tmp_path, 'screenshots')
    assert plan['en-US']['APP_IPHONE_67']
    assert plan['de-DE']['APP_IPAD_PRO_3GEN_129']


def test_plan_from_a_flat_tree_needs_a_locale(tmp_path):
    shot(tmp_path, 'phone', '01.png')
    plan = media.plan_from_tree(tmp_path, 'screenshots', locale='fr-FR')
    assert list(plan) == ['fr-FR']


def test_plan_from_a_flat_tree_for_every_locale(tmp_path):
    shot(tmp_path, 'phone', '01.png')
    plan = media.plan_from_tree(tmp_path, 'screenshots', all_locales=True,
                                known_locales=['en-US', 'de-DE'])
    assert sorted(plan) == ['de-DE', 'en-US']


def test_plan_for_videos_from_a_device_first_tree(tmp_path):
    for locale in ('en-US', 'de-DE'):
        path = tmp_path / 'iPhone' / locale / 'app_preview.mp4'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not a real video')
    plan = media.plan_from_tree(tmp_path, 'previews')
    assert plan['en-US']['IPHONE_67']
    assert plan['de-DE']['IPHONE_67']


def test_sync_skips_a_set_whose_checksums_match(tmp_path, capsys):
    file = shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '01.png')
    checksum = media.md5_of(file)
    client = FakeClient(collections={
        '/v1/appStoreVersionLocalizations/l1/appScreenshotSets': [
            {'id': 's1', 'attributes': {'screenshotDisplayType': 'APP_IPHONE_67'}}],
        '/v1/appScreenshotSets/s1/appScreenshots': [
            {'id': 'a1', 'attributes': {'sourceFileChecksum': checksum}}],
    })
    changed, unchanged = media.sync_sets(client, media.SCREENSHOT_SPEC, 'l1',
                                         {'APP_IPHONE_67': [file]}, 'en-US')
    assert (changed, unchanged) == (0, 1)
    assert 'up to date' in capsys.readouterr().out


def test_sync_replaces_a_set_that_changed(tmp_path):
    file = shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '01.png')
    client = FakeClient(
        routes={('POST', '/v1/appScreenshots'): {'data': {
            'id': 'new', 'attributes': {'uploadOperations': [
                {'method': 'PUT', 'url': 'https://upload.test/1', 'offset': 0,
                 'length': 10, 'requestHeaders': []}]}}}},
        collections={
            '/v1/appStoreVersionLocalizations/l1/appScreenshotSets': [
                {'id': 's1', 'attributes': {'screenshotDisplayType': 'APP_IPHONE_67'}}],
            '/v1/appScreenshotSets/s1/appScreenshots': [
                {'id': 'old', 'attributes': {'sourceFileChecksum': 'different'}}],
        })
    changed, _unchanged = media.sync_sets(client, media.SCREENSHOT_SPEC, 'l1',
                                          {'APP_IPHONE_67': [file]}, 'en-US')
    assert changed == 1
    assert ('DELETE', '/v1/appScreenshots/old', None) in client.calls
    assert client.uploads                        # the file went up
    committed = next(body for method, path, body in client.calls
                     if path == '/v1/appScreenshots/new')
    assert committed['data']['attributes']['uploaded'] is True


def test_sync_dry_run_changes_nothing(tmp_path):
    file = shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '01.png')
    client = FakeClient(collections={
        '/v1/appStoreVersionLocalizations/l1/appScreenshotSets': [],
    })
    changed, _unchanged = media.sync_sets(client, media.SCREENSHOT_SPEC, 'l1',
                                          {'APP_IPHONE_67': [file]}, 'en-US',
                                          dry_run=True)
    assert changed == 1
    assert not client.uploads


def test_sync_with_missing_only_keeps_what_the_store_has(tmp_path, capsys):
    file = shot(tmp_path, 'en-US', 'screenshots', 'iphone-6.9', '01.png')
    client = FakeClient(collections={
        '/v1/appStoreVersionLocalizations/l1/appScreenshotSets': [
            {'id': 's1', 'attributes': {'screenshotDisplayType': 'APP_IPHONE_67'}}],
        '/v1/appScreenshotSets/s1/appScreenshots': [
            {'id': 'a1', 'attributes': {'sourceFileChecksum': 'different'}}],
    })
    changed, unchanged = media.sync_sets(client, media.SCREENSHOT_SPEC, 'l1',
                                         {'APP_IPHONE_67': [file]}, 'en-US',
                                         missing_only=True)
    assert (changed, unchanged) == (0, 1)
    assert '--missing-only' in capsys.readouterr().out


def test_sync_refuses_more_than_three_previews(tmp_path):
    files = []
    for index in range(4):
        path = tmp_path / f'{index}.mp4'
        path.write_bytes(b'x')
        files.append(path)
    client = FakeClient(collections={
        '/v1/appStoreVersionLocalizations/l1/appPreviewSets': []})
    failures = []
    media.sync_sets(client, media.PREVIEW_SPEC, 'l1', {'IPHONE_67': files}, 'en-US',
                    failures=failures)
    assert failures and 'at most 3' in failures[0][1]


def test_push_assets_skips_a_locale_without_a_localization(tmp_path, capsys):
    root = write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(root))
    assets_dir = tmp_path / 'assets'
    shot(assets_dir, 'fr-FR', 'screenshots', 'iphone-6.9', '01.png')
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1')]))
    assert media.cmd_push_assets(ws, assets_dir=assets_dir, client=client) == 1
    assert 'no localization' in capsys.readouterr().out


# -- drift and the safety of pull ---------------------------------------------

def store_with(fields, version='2.1'):
    """A fake client whose store holds `fields` for en-US."""
    version_attrs = {'id': 'v1', 'attributes': {'versionString': version,
                                                'appStoreState': 'READY_FOR_SALE'}}
    client = FakeClient(collections={
        '/v1/apps/123/appStoreVersions': [version_attrs],
        '/v1/apps/123/appInfos': [{'id': 'i1',
                                   'attributes': {'appStoreState': 'READY_FOR_SALE'}}],
        '/v1/appStoreVersions/v1/appStoreVersionLocalizations': [
            localization('en-US', 'l1',
                         **{k: v for k, v in fields.items()
                            if k in ('keywords', 'description', 'promotionalText',
                                     'whatsNew', 'marketingUrl', 'supportUrl')})],
        '/v1/appInfos/i1/appInfoLocalizations': [
            localization('en-US', 'a1',
                         **{k: v for k, v in fields.items()
                            if k in ('name', 'subtitle', 'privacyPolicyUrl')})],
    })
    return client


LIVE = {'name': 'Trailwise', 'subtitle': 'Offline Maps', 'keywords': 'gps,compass',
        'description': 'What the app does.',
        'supportUrl': 'https://example.test/support'}


def test_pull_check_reports_no_drift(ws, capsys):
    client = store_with(LIVE)
    assert pull.cmd_pull(ws, check=True, client=client) == 0
    assert 'matches the store' in capsys.readouterr().out


def test_pull_check_reports_drift_and_writes_nothing(ws, capsys):
    before = (ws.versions_dir / '2.1' / 'titles.yaml').read_text(encoding='utf-8')
    client = store_with({**LIVE, 'name': 'Renamed in the web interface'})
    assert pull.cmd_pull(ws, check=True, client=client) == pull.EXIT_DRIFT
    printed = capsys.readouterr().out
    assert 'differ from the store' in printed
    assert 'Renamed in the web interface' in printed
    assert (ws.versions_dir / '2.1' / 'titles.yaml').read_text(encoding='utf-8') == before


def test_pull_refuses_to_lose_local_work(ws, capsys):
    client = store_with({**LIVE, 'keywords': 'gps'})
    assert pull.cmd_pull(ws, client=client) == pull.EXIT_DRIFT
    printed = capsys.readouterr().out
    assert 'aso pull --force' in printed
    # The draft is still there.
    assert 'gps,compass' in (ws.versions_dir / '2.1' / 'titles.yaml').read_text()


def test_pull_force_overwrites(ws):
    client = store_with({**LIVE, 'keywords': 'gps'})
    assert pull.cmd_pull(ws, force=True, client=client) == 0
    assert loader.load_version_raw(ws.versions_dir / '2.1')['en-US']['keywords'] == 'gps'


def test_pull_overwrites_freely_when_the_change_came_from_the_store(ws):
    from aso_advisor import db

    # The workspace matches the last pull, so nothing local is at risk.
    conn = db.connect(ws.db_path)
    db.save_sync_snapshot(conn, '2.1',
                          loader.load_version_raw(ws.versions_dir / '2.1'), 'pull')
    conn.close()
    client = store_with({**LIVE, 'name': 'Renamed by a teammate'})
    assert pull.cmd_pull(ws, client=client) == 0
    assert (loader.load_version_raw(ws.versions_dir / '2.1')['en-US']['name']
            == 'Renamed by a teammate')


def test_pull_remembers_what_it_read(ws):
    from aso_advisor import db

    client = store_with(LIVE)
    pull.cmd_pull(ws, force=True, client=client)
    conn = db.connect(ws.db_path)
    remembered, stamp, source = db.load_sync_snapshot(conn, '2.1')
    conn.close()
    assert remembered['en-US']['keywords'] == 'gps,compass'
    assert source == 'pull' and stamp


# -- the push diff ------------------------------------------------------------

def test_push_shows_the_values_that_would_change(ws, capsys):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='old,words')],
        info_locales=[localization('en-US', 'a1', name='Old Name')]))
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'), dry_run=True,
                  client=client)
    printed = capsys.readouterr().out
    assert '- store old,words' in printed
    assert '+ new   gps,compass' in printed
    assert 'Old Name' in printed and 'Trailwise' in printed


def test_push_sends_nothing_when_the_store_already_matches(ws, capsys):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='gps,compass',
                                      description='What the app does.',
                                      supportUrl='https://example.test/support')],
        info_locales=[localization('en-US', 'a1', name='Trailwise',
                                   subtitle='Offline Maps')]))
    assert push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'),
                         client=client) == 0
    assert 'nothing to send' in capsys.readouterr().out
    assert not [c for c in client.calls if c[0] in ('PATCH', 'POST')]


def test_push_skips_the_locales_that_already_match(ws, capsys):
    root = write_workspace(ws.root.parent / 'aso2', versions={'2.1': {'m.yaml': """\
locales:
  en-US:
    name: Trailwise
    keywords: new,words
  de-DE:
    name: Trailwise
    keywords: karte
"""}})
    workspace_two = workspace.load(explicit=str(root))
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='old'),
                         localization('de-DE', 'l2', keywords='karte')],
        info_locales=[localization('en-US', 'a1', name='Trailwise'),
                      localization('de-DE', 'a2', name='Trailwise')]))
    push.cmd_push(workspace_two, loader.load_version_raw(root / 'versions' / '2.1'),
                  client=client)
    printed = capsys.readouterr().out
    assert 'Sent: 1' in printed and 'Already correct: 1' in printed
    assert not any(path.endswith('/l2') for _m, path, _b in client.calls)


def test_push_keeps_a_backup_of_the_store(ws):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='old,words')],
        info_locales=[localization('en-US', 'a1', name='Old Name')]))
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'), client=client)
    backups = sorted((ws.state_dir / 'backups').iterdir())
    assert backups
    saved = loader.load_version_raw(backups[-1])
    assert saved['en-US']['keywords'] == 'old,words'
    assert (backups[-1] / 'README.txt').is_file()


def test_push_can_skip_the_backup(ws):
    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='old')],
        info_locales=[localization('en-US', 'a1', name='Old')]))
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'), backup=False,
                  client=client)
    assert not (ws.state_dir / 'backups').exists()


def test_push_remembers_what_it_sent(ws):
    from aso_advisor import db

    client = FakeClient(collections=base_collections(
        version_locales=[localization('en-US', 'l1', keywords='old')],
        info_locales=[localization('en-US', 'a1', name='Old')]))
    push.cmd_push(ws, loader.load_version_raw(ws.versions_dir / '2.1'),
                  version_name='2.1', client=client)
    conn = db.connect(ws.db_path)
    remembered, _stamp, source = db.load_sync_snapshot(conn, '2.1')
    conn.close()
    assert remembered['en-US']['keywords'] == 'gps,compass'
    assert source == 'push'
