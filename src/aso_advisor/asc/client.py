"""The App Store Connect API client: credentials, JWT, HTTP, and lookups.

This layer is the only part of the tool that WRITES to App Store Connect. It
needs a private key that you make yourself. Read `docs/app-store-connect.md`
for the steps, or run `aso auth` for a short version in the terminal.

The transport is `urllib` from the standard library. The one extra dependency
is PyJWT, because Apple wants an ES256 token:

    pip install 'aso-advisor[sync]'
"""

import contextlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API_BASE = 'https://api.appstoreconnect.apple.com'
TIMEOUT_SECONDS = 60
UPLOAD_TIMEOUT_SECONDS = 300
TOKEN_LIFETIME_SECONDS = 20 * 60

# The environment variable names are the same as the ones in the metadata
# scripts that this layer comes from, so an existing .env file still works.
ENV_KEY_ID = 'APP_STORE_CONNECT_KEY_ID'
ENV_ISSUER_ID = 'APP_STORE_CONNECT_ISSUER_ID'
ENV_KEY_PATH = 'APP_STORE_CONNECT_PRIVATE_KEY_PATH'
ENV_KEY_VALUE = 'APP_STORE_CONNECT_PRIVATE_KEY'   # the key itself, for CI
ENV_APP_ID = 'APP_STORE_CONNECT_APP_ID'

EDITABLE_VERSION_STATES = {
    'PREPARE_FOR_SUBMISSION',
    'DEVELOPER_REJECTED',
    'REJECTED',
    'METADATA_REJECTED',
    'WAITING_FOR_REVIEW',
}

# Editable, but only with --force. A change here can restart the review.
PROTECTED_VERSION_STATES = {'WAITING_FOR_REVIEW'}

# The states of a published version, in the order of preference.
LIVE_VERSION_STATES = [
    'READY_FOR_SALE',
    'PENDING_DEVELOPER_RELEASE',
    'PENDING_APPLE_RELEASE',
    'REPLACED_WITH_NEW_VERSION',
]

# YAML key -> the attribute name of App Store Connect.
VERSION_LOCALIZATION_FIELDS = {
    'description': 'description',
    'keywords': 'keywords',
    'promotional_text': 'promotionalText',
    'whats_new': 'whatsNew',
    'marketing_url': 'marketingUrl',
    'support_url': 'supportUrl',
}

APP_INFO_LOCALIZATION_FIELDS = {
    'name': 'name',
    'subtitle': 'subtitle',
    'privacy_policy_url': 'privacyPolicyUrl',
}

VERSION_ASC_TO_YAML = {asc: y for y, asc in VERSION_LOCALIZATION_FIELDS.items()}
APP_INFO_ASC_TO_YAML = {asc: y for y, asc in APP_INFO_LOCALIZATION_FIELDS.items()}

HOW_TO_MAKE_A_KEY = """\
How to make an App Store Connect API key:

  1. Sign in to https://appstoreconnect.apple.com/.
  2. Go to Users and Access → Integrations → App Store Connect API.
  3. Select Team Keys, then press the plus button.
  4. Give the key a name and the role "App Manager" or higher.
  5. Press Generate, then Download the .p8 file. Apple gives you ONE
     download. Keep the file safe, for example in
     ~/.appstoreconnect/keys/AuthKey_XXXXXXXXXX.p8.
  6. Note the Key ID from the table, and the Issuer ID at the top of the page.

Then tell the tool about the key, with environment variables:

  export APP_STORE_CONNECT_KEY_ID=ABCDE12345
  export APP_STORE_CONNECT_ISSUER_ID=00000000-0000-0000-0000-000000000000
  export APP_STORE_CONNECT_PRIVATE_KEY_PATH=~/.appstoreconnect/keys/AuthKey_ABCDE12345.p8

or in the `asc:` block of your aso.yaml, or in a .env file in the workspace.
The app identifier comes from `app.track_id` in aso.yaml.

Never put the .p8 file in version control. Treat it like an SSH key.
Full instructions: docs/app-store-connect.md
"""


class ASCAuthError(Exception):
    """The credentials are missing, or they are not complete."""


class ASCError(Exception):
    """App Store Connect answered with an error."""

    def __init__(self, status, errors, raw=''):
        self.status = status
        self.errors = errors or []
        self.raw = raw
        super().__init__(self._format())

    def _format(self):
        if not self.errors:
            return f'HTTP {self.status}: {self.raw[:500]}'
        lines = [f'HTTP {self.status}:']
        for err in self.errors:
            code = err.get('code', '?')
            title = err.get('title', '')
            detail = err.get('detail', '')
            source = err.get('source') or {}
            where = ''
            if isinstance(source, dict):
                if 'pointer' in source:
                    where = f' [pointer={source["pointer"]}]'
                elif 'parameter' in source:
                    where = f' [parameter={source["parameter"]}]'
            lines.append(f'  - {code}: {title}{where}')
            if detail and detail != title:
                lines.append(f'      {detail}')
        return '\n'.join(lines)


# -- credentials --------------------------------------------------------------

def read_env_file(path):
    """Read a simple KEY=VALUE file. Returns {} when the file is missing."""
    path = Path(path)
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


@dataclass
class Credentials:
    key_id: str
    issuer_id: str
    private_key: str
    app_id: str
    key_path: str = ''

    @classmethod
    def resolve(cls, ws=None):
        """Find the credentials.

        The order is: environment variables, then a .env file in the workspace
        or in the current directory, then the `asc:` block of aso.yaml. The app
        identifier falls back to `app.track_id`.
        """
        sources = dict(os.environ)
        for candidate in ([ws.root / '.env'] if ws else []) + [Path.cwd() / '.env']:
            for key, value in read_env_file(candidate).items():
                sources.setdefault(key, value)

        asc_config = getattr(ws.config, 'asc', None) if ws else None
        key_id = sources.get(ENV_KEY_ID) or (asc_config.key_id if asc_config else '')
        issuer_id = sources.get(ENV_ISSUER_ID) or (asc_config.issuer_id if asc_config else '')
        key_path = sources.get(ENV_KEY_PATH) or (asc_config.private_key_path
                                                 if asc_config else '')
        key_value = sources.get(ENV_KEY_VALUE, '')
        app_id = (sources.get(ENV_APP_ID)
                  or (asc_config.app_id if asc_config else '')
                  or (str(ws.config.app.track_id) if ws and ws.config.app.track_id else ''))

        missing = []
        if not key_id:
            missing.append(f'{ENV_KEY_ID} (or asc.key_id)')
        if not issuer_id:
            missing.append(f'{ENV_ISSUER_ID} (or asc.issuer_id)')
        if not (key_path or key_value):
            missing.append(f'{ENV_KEY_PATH} (or asc.private_key_path)')
        if not app_id:
            missing.append(f'{ENV_APP_ID} (or app.track_id in aso.yaml)')
        if missing:
            raise ASCAuthError('These credentials are missing:\n  - '
                               + '\n  - '.join(missing) + '\n\n' + HOW_TO_MAKE_A_KEY)

        private_key = key_value
        resolved_path = ''
        if not private_key:
            path = Path(key_path).expanduser()
            if not path.is_absolute() and ws:
                candidate = (ws.root / path)
                if candidate.is_file():
                    path = candidate
            if not path.is_file():
                raise ASCAuthError(
                    f'The private key file is not there: {path}\n\n'
                    'Apple lets you download a .p8 file one time only. If it is lost, '
                    'revoke the key in App Store Connect and make a new one.\n\n'
                    + HOW_TO_MAKE_A_KEY)
            private_key = path.read_text(encoding='utf-8')
            resolved_path = str(path)
        if 'PRIVATE KEY' not in private_key:
            raise ASCAuthError(
                f'{resolved_path or "The private key"} does not look like a .p8 key. '
                'The file must start with "-----BEGIN PRIVATE KEY-----".')
        return cls(key_id=key_id, issuer_id=issuer_id, private_key=private_key,
                   app_id=str(app_id), key_path=resolved_path)


def make_jwt(creds):
    """A signed ES256 token that is valid for 20 minutes."""
    try:
        import jwt
    except ImportError as exc:                      # pragma: no cover - import guard
        raise ASCAuthError(
            'The App Store Connect commands need PyJWT.\n'
            "Install it with:  pip install 'aso-advisor[sync]'") from exc
    now = int(time.time())
    payload = {
        'iss': creds.issuer_id,
        'iat': now,
        'exp': now + TOKEN_LIFETIME_SECONDS,
        'aud': 'appstoreconnect-v1',
    }
    try:
        return jwt.encode(payload, creds.private_key, algorithm='ES256',
                          headers={'kid': creds.key_id, 'typ': 'JWT'})
    except Exception as exc:                        # noqa: BLE001 - any crypto error
        raise ASCAuthError(
            f'The token could not be signed: {exc}\n'
            'Check that the .p8 file belongs to the key identifier that you gave, '
            "and that PyJWT has its crypto extra: pip install 'aso-advisor[sync]'"
        ) from exc


# -- the client ---------------------------------------------------------------

class ASCClient:
    """A small client over the App Store Connect API."""

    def __init__(self, creds, verbose=False):
        self.creds = creds
        self.verbose = verbose
        self._token = None
        self._token_time = 0.0

    def token(self):
        if self._token is None or (time.time() - self._token_time) > TOKEN_LIFETIME_SECONDS - 120:
            self._token = make_jwt(self.creds)
            self._token_time = time.time()
        return self._token

    def request(self, method, path, params=None, json_body=None):
        url = path if path.startswith('http') else f'{API_BASE}{path}'
        if params:
            url = f'{url}?{urllib.parse.urlencode(params)}'
        headers = {'Authorization': f'Bearer {self.token()}', 'Accept': 'application/json'}
        body = None
        if json_body is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(json_body).encode('utf-8')

        if self.verbose:
            print(f'--> {method} {url}')
            if json_body is not None:
                print(f'    {json.dumps(json_body)[:2000]}')

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                text = response.read().decode('utf-8', 'replace')
                status = response.status
        except urllib.error.HTTPError as exc:
            text = exc.read().decode('utf-8', 'replace')
            errors = []
            with contextlib.suppress(ValueError):
                errors = json.loads(text).get('errors', [])
            if self.verbose:
                print(f'<-- {exc.code}\n    {text[:2000]}')
            raise ASCError(exc.code, errors, text) from exc
        except urllib.error.URLError as exc:
            raise ASCError(0, [], f'No answer from {url}: {exc.reason}') from exc

        if self.verbose:
            print(f'<-- {status}\n    {text[:2000]}')
        if not text:
            return {}
        try:
            return json.loads(text)
        except ValueError:
            return {}

    def get_all(self, path, params=None):
        """Follow the pages and return the joined `data` array."""
        params = dict(params or {})
        params.setdefault('limit', 200)
        out, next_url = [], None
        while True:
            page = self.request('GET', next_url) if next_url \
                else self.request('GET', path, params=params)
            out.extend(page.get('data', []))
            next_url = (page.get('links') or {}).get('next')
            if not next_url:
                return out

    def upload_chunk(self, operation, data):
        """Send one chunk of an asset, as App Store Connect asked."""
        headers = {h['name']: h['value'] for h in operation.get('requestHeaders', [])}
        offset = operation.get('offset', 0)
        length = operation.get('length', len(data))
        chunk = data[offset:offset + length]
        request = urllib.request.Request(operation['url'], data=chunk, headers=headers,
                                         method=operation.get('method', 'PUT'))
        try:
            with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT_SECONDS) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', 'replace')
            raise ASCError(exc.code, [], body) from exc
        except urllib.error.URLError as exc:
            raise ASCError(0, [], f'The chunk upload failed: {exc.reason}') from exc

    def whoami(self):
        """The app record. Use it to test the credentials."""
        data = self.request('GET', f'/v1/apps/{self.creds.app_id}')
        return (data.get('data') or {}).get('attributes') or {}


# -- versions and localizations -----------------------------------------------

def find_editable_version(client, allow_waiting_for_review=False):
    versions = client.get_all(
        f'/v1/apps/{client.creds.app_id}/appStoreVersions',
        params={'filter[appStoreState]': ','.join(sorted(EDITABLE_VERSION_STATES)),
                'limit': 10})
    if not versions:
        raise ASCError(0, [], 'No editable App Store version. Make one in App Store '
                              'Connect first.')
    for version in versions:
        if version.get('attributes', {}).get('appStoreState') not in PROTECTED_VERSION_STATES:
            return version
    if allow_waiting_for_review:
        return versions[0]
    raise ASCError(0, [], 'The newest editable version is in WAITING_FOR_REVIEW. '
                          'Use --force to change it.')


def find_live_version(client):
    versions = client.get_all(
        f'/v1/apps/{client.creds.app_id}/appStoreVersions',
        params={'filter[appStoreState]': ','.join(LIVE_VERSION_STATES), 'limit': 20})
    if not versions:
        raise ASCError(0, [], 'No live App Store version. The app is not published yet. '
                              'Use --editable to read the version that you prepare.')
    for state in LIVE_VERSION_STATES:
        for version in versions:
            if version.get('attributes', {}).get('appStoreState') == state:
                return version
    return versions[0]


def _find_app_info(client, states):
    infos = client.get_all(f'/v1/apps/{client.creds.app_id}/appInfos')
    for state in states:
        for info in infos:
            if info.get('attributes', {}).get('appStoreState') == state:
                return info
    return None


def find_live_app_info(client):
    info = _find_app_info(client, LIVE_VERSION_STATES)
    if info is None:
        raise ASCError(0, [], 'No live appInfo for this app.')
    return info


def find_editable_app_info(client):
    info = _find_app_info(client, ['PREPARE_FOR_SUBMISSION', *sorted(EDITABLE_VERSION_STATES)])
    if info is None:
        raise ASCError(0, [], 'No editable appInfo for this app.')
    return info


def list_version_localizations(client, version_id):
    items = client.get_all(f'/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations')
    return {item['attributes']['locale']: item for item in items}


def list_app_info_localizations(client, app_info_id):
    items = client.get_all(f'/v1/appInfos/{app_info_id}/appInfoLocalizations')
    return {item['attributes']['locale']: item for item in items}


def project_yaml(fields, mapping):
    """Take the YAML keys of `mapping` and rename them for the API."""
    out = {}
    for yaml_key, asc_key in mapping.items():
        if yaml_key in fields and fields[yaml_key] is not None:
            out[asc_key] = fields[yaml_key]
    return out


def validate_locale_fields(locale, fields):
    """The length errors of one locale, as readable lines."""
    from ..model import LIMITS

    errors = []
    for key, limit in LIMITS.items():
        value = fields.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f'{locale}.{key}: expected text, found {type(value).__name__}')
            continue
        if len(value) > limit:
            errors.append(f'{locale}.{key}: {len(value)} characters, the limit is {limit}')
    return errors


def select_locales(locales, only=None):
    """Iterate over (code, fields), for one locale or for all of them."""
    if only:
        if only not in locales:
            raise ASCError(0, [], f'Locale {only!r} is not in the metadata.')
        yield only, locales[only]
        return
    yield from sorted(locales.items())
