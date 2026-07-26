"""Tests for the App Store Connect client. No test reaches the network."""

import json

import pytest

from aso_advisor import workspace
from aso_advisor.asc import client as asc
from conftest import write_workspace

CONFIG_WITH_ASC = """\
version: 1
app:
  track_id: 999
asc:
  key_id: FROMYAML
  issuer_id: issuer-from-yaml
  private_key_path: key.p8
"""

FAKE_KEY = '-----BEGIN PRIVATE KEY-----\nMIGTAgEA\n-----END PRIVATE KEY-----\n'


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (asc.ENV_KEY_ID, asc.ENV_ISSUER_ID, asc.ENV_KEY_PATH,
                 asc.ENV_KEY_VALUE, asc.ENV_APP_ID):
        monkeypatch.delenv(name, raising=False)


def make_workspace(tmp_path, config=CONFIG_WITH_ASC, with_key=True):
    root = write_workspace(tmp_path / 'aso', config=config)
    if with_key:
        (root / 'key.p8').write_text(FAKE_KEY)
    return workspace.load(explicit=str(root))


# -- credentials --------------------------------------------------------------

def test_credentials_come_from_the_configuration(tmp_path):
    creds = asc.Credentials.resolve(make_workspace(tmp_path))
    assert creds.key_id == 'FROMYAML'
    assert creds.issuer_id == 'issuer-from-yaml'
    assert creds.app_id == '999'                 # from app.track_id
    assert creds.private_key == FAKE_KEY


def test_the_environment_wins_over_the_configuration(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path)
    monkeypatch.setenv(asc.ENV_KEY_ID, 'FROMENV')
    monkeypatch.setenv(asc.ENV_APP_ID, '4242')
    creds = asc.Credentials.resolve(ws)
    assert creds.key_id == 'FROMENV'
    assert creds.app_id == '4242'


def test_an_env_file_in_the_workspace_is_read(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path, config='version: 1\napp:\n  track_id: 7\n')
    (ws.root / '.env').write_text(
        '# a comment\n'
        f'{asc.ENV_KEY_ID}="FROMFILE"\n'
        f'{asc.ENV_ISSUER_ID}=issuer\n'
        f'{asc.ENV_KEY_PATH}={ws.root / "key.p8"}\n')
    monkeypatch.chdir(tmp_path)
    creds = asc.Credentials.resolve(ws)
    assert creds.key_id == 'FROMFILE'
    assert creds.app_id == '7'


def test_the_key_may_come_from_a_variable_for_a_build_pipeline(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path, config='version: 1\napp:\n  track_id: 7\n',
                        with_key=False)
    monkeypatch.setenv(asc.ENV_KEY_ID, 'A')
    monkeypatch.setenv(asc.ENV_ISSUER_ID, 'B')
    monkeypatch.setenv(asc.ENV_KEY_VALUE, FAKE_KEY)
    creds = asc.Credentials.resolve(ws)
    assert creds.private_key == FAKE_KEY
    assert creds.key_path == ''


def test_missing_credentials_explain_how_to_make_a_key(tmp_path):
    ws = make_workspace(tmp_path, config='version: 1\n', with_key=False)
    with pytest.raises(asc.ASCAuthError) as caught:
        asc.Credentials.resolve(ws)
    message = str(caught.value)
    assert 'APP_STORE_CONNECT_KEY_ID' in message
    assert 'Users and Access' in message         # the instructions come with it


def test_a_missing_key_file_says_which_path(tmp_path):
    ws = make_workspace(tmp_path, with_key=False)
    with pytest.raises(asc.ASCAuthError, match='not there'):
        asc.Credentials.resolve(ws)


def test_a_file_that_is_not_a_key_is_refused(tmp_path):
    ws = make_workspace(tmp_path, with_key=False)
    (ws.root / 'key.p8').write_text('this is not a key')
    with pytest.raises(asc.ASCAuthError, match='does not look like'):
        asc.Credentials.resolve(ws)


def test_read_env_file_of_a_missing_file(tmp_path):
    assert asc.read_env_file(tmp_path / 'nothing') == {}


# -- errors -------------------------------------------------------------------

def test_the_error_message_names_the_field():
    error = asc.ASCError(409, [{'code': 'ENTITY_ERROR.ATTRIBUTE.INVALID',
                                'title': 'An attribute value is not acceptable',
                                'detail': 'keywords is too long',
                                'source': {'pointer': '/data/attributes/keywords'}}])
    text = str(error)
    assert 'ENTITY_ERROR.ATTRIBUTE.INVALID' in text
    assert 'keywords is too long' in text
    assert 'pointer=/data/attributes/keywords' in text


def test_an_error_without_a_body_still_reads_well():
    assert 'HTTP 500' in str(asc.ASCError(500, [], 'gateway trouble'))


# -- the HTTP layer -----------------------------------------------------------

class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()
        self.status = 200

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_get_all_follows_the_pages(monkeypatch):
    creds = asc.Credentials(key_id='A', issuer_id='B', private_key=FAKE_KEY, app_id='1')
    client = asc.ASCClient(creds)
    monkeypatch.setattr(client, 'token', lambda: 'token')
    pages = [
        {'data': [{'id': '1'}], 'links': {'next': 'https://example.test/page2'}},
        {'data': [{'id': '2'}], 'links': {}},
    ]
    seen = []

    def fake_open(request, timeout=None):
        seen.append(request.full_url)
        return FakeResponse(pages[len(seen) - 1])

    monkeypatch.setattr(asc.urllib.request, 'urlopen', fake_open)
    assert [item['id'] for item in client.get_all('/v1/things')] == ['1', '2']
    assert seen[1] == 'https://example.test/page2'


def test_the_request_carries_the_token(monkeypatch):
    creds = asc.Credentials(key_id='A', issuer_id='B', private_key=FAKE_KEY, app_id='1')
    client = asc.ASCClient(creds)
    monkeypatch.setattr(client, 'token', lambda: 'the-token')
    captured = {}

    def fake_open(request, timeout=None):
        captured['auth'] = request.headers.get('Authorization')
        captured['method'] = request.get_method()
        return FakeResponse({'data': {}})

    monkeypatch.setattr(asc.urllib.request, 'urlopen', fake_open)
    client.request('PATCH', '/v1/things/1', json_body={'data': {}})
    assert captured['auth'] == 'Bearer the-token'
    assert captured['method'] == 'PATCH'


# -- validation ---------------------------------------------------------------

def test_validation_finds_a_field_that_is_too_long():
    errors = asc.validate_locale_fields('en-US', {'name': 'x' * 31, 'keywords': 'gps'})
    assert len(errors) == 1
    assert 'en-US.name' in errors[0]


def test_validation_accepts_correct_fields():
    assert asc.validate_locale_fields('en-US', {'name': 'ok', 'subtitle': 'also ok'}) == []


def test_project_yaml_renames_the_keys():
    out = asc.project_yaml({'promotional_text': 'hello', 'name': 'skip'},
                           asc.VERSION_LOCALIZATION_FIELDS)
    assert out == {'promotionalText': 'hello'}


def test_select_locales_of_one_locale():
    assert list(asc.select_locales({'en-US': {}, 'de-DE': {}}, 'de-DE')) == [('de-DE', {})]


def test_select_locales_of_an_unknown_locale():
    with pytest.raises(asc.ASCError, match='not in the metadata'):
        list(asc.select_locales({'en-US': {}}, 'fr-FR'))
