"""A read-only client for the PUBLIC endpoints of Apple.

No account and no API key are necessary. The tool reads three sources:

- **iTunes Search and Lookup.** The search endpoint returns the same ordered
  list of apps that the store shows, so the position of your app in that list
  is a real rank. The lookup endpoint returns the details of an app.
- **MZSearchHints.** The autocomplete of the App Store. Apple sorts the
  suggestions by popularity, so the order is the closest free substitute for
  search volume.
- **The customer reviews RSS feed.** The most recent reviews with their stars.

Every request goes through `_fetch()`. That function keeps the answer in the
SQLite database of the workspace and waits between two uncached requests. Apple
allows about 20 requests per minute. A second run of the same command is
instant.

These endpoints are public but they are not a documented, supported API. Apple
can change them. The tool fails softly when an endpoint answers something that
it does not understand.
"""

import json
import plistlib
import time
import urllib.error
import urllib.parse
import urllib.request

from . import db
from .storefronts import STOREFRONT_IDS

USER_AGENT = 'aso-advisor/1.0 (+https://github.com/AdmTal/aso-advisor)'
CACHE_TTL_HOURS = 12
THROTTLE_SECONDS = 3.1     # about 19 requests per minute
TIMEOUT_SECONDS = 25
_last_hit = 0.0


class StoreAPIError(Exception):
    """A public endpoint of Apple did not answer correctly."""


def _throttle():
    global _last_hit
    wait = THROTTLE_SECONDS - (time.time() - _last_hit)
    if wait > 0:
        time.sleep(wait)


def _get(url, headers=None):
    request = urllib.request.Request(
        url, headers={'User-Agent': USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        raise StoreAPIError(f'{exc.code} from {url}') from exc
    except urllib.error.URLError as exc:
        raise StoreAPIError(f'No answer from {url}: {exc.reason}') from exc


def _fetch(conn, url, headers=None, ttl_hours=CACHE_TTL_HOURS, cache_key=None):
    """GET with a cache and a wait. Returns the body as text."""
    global _last_hit
    key = cache_key or url
    if ttl_hours > 0:
        cached = db.cache_get(conn, key, ttl_hours)
        if cached is not None:
            return cached
    _throttle()
    body = _get(url, headers)
    _last_hit = time.time()
    db.cache_put(conn, key, body)
    return body


# -- search and lookup --------------------------------------------------------

def search(conn, term, country='us', limit=200, ttl_hours=CACHE_TTL_HOURS):
    """The ordered list of apps that the store returns for `term`."""
    query = urllib.parse.urlencode({
        'term': term, 'country': country, 'entity': 'software',
        'media': 'software', 'limit': max(1, min(limit, 200)),
    })
    body = _fetch(conn, f'https://itunes.apple.com/search?{query}', ttl_hours=ttl_hours)
    try:
        return json.loads(body).get('results', [])
    except json.JSONDecodeError as exc:
        raise StoreAPIError(f'The search answer for {term!r} is not JSON.') from exc


def lookup(conn, track_ids=None, bundle_id=None, country='us', ttl_hours=CACHE_TTL_HOURS):
    """The details of up to 100 apps in ONE request, or of one bundle."""
    if bundle_id:
        query = urllib.parse.urlencode({'bundleId': bundle_id, 'country': country})
    else:
        query = urllib.parse.urlencode(
            {'id': ','.join(str(i) for i in track_ids or []), 'country': country})
    body = _fetch(conn, f'https://itunes.apple.com/lookup?{query}', ttl_hours=ttl_hours)
    try:
        return json.loads(body).get('results', [])
    except json.JSONDecodeError as exc:
        raise StoreAPIError('The lookup answer is not JSON.') from exc


def rank_of(results, track_id):
    """The position of `track_id` in a result list, counted from 1, or None."""
    for position, app in enumerate(results, 1):
        if app.get('trackId') == track_id:
            return position
    return None


# -- autocomplete -------------------------------------------------------------

def hints(conn, term, country='us', ttl_hours=CACHE_TTL_HOURS):
    """The autocomplete suggestions for `term`, in the order of Apple.

    Position 1 is the completion with the most searches.
    """
    storefront = STOREFRONT_IDS.get(country.lower())
    if storefront is None:
        raise StoreAPIError(
            f'No storefront identifier for country {country!r}. '
            'Add it to storefronts.STOREFRONT_IDS or use another country.')
    query = urllib.parse.urlencode({'clientApplication': 'Software', 'term': term})
    url = f'https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints?{query}'
    # The storefront header changes the answer, so it belongs in the cache key.
    body = _fetch(conn, url, headers={'X-Apple-Store-Front': f'{storefront}-1,29'},
                  ttl_hours=ttl_hours, cache_key=f'{url}#sf={storefront}')
    return _parse_hints(body)


def _parse_hints(body):
    try:
        data = plistlib.loads(body.encode('utf-8'))
    except Exception as exc:                       # noqa: BLE001 - any plist error
        raise StoreAPIError('The autocomplete answer is not a property list.') from exc
    return [h.get('term', '') for h in data.get('hints', []) if h.get('term')]


# -- reviews ------------------------------------------------------------------

def reviews(conn, track_id, country='us', pages=2, ttl_hours=CACHE_TTL_HOURS):
    """The most recent reviews: [{rating, title, body, version, date, author}]."""
    out = []
    for page in range(1, pages + 1):
        url = (f'https://itunes.apple.com/{country}/rss/customerreviews/'
               f'page={page}/id={track_id}/sortby=mostrecent/json')
        try:
            feed = json.loads(_fetch(conn, url, ttl_hours=ttl_hours)).get('feed', {})
        except (StoreAPIError, json.JSONDecodeError):
            break     # A storefront with no reviews answers 404 or HTML.
        entries = feed.get('entry') or []
        if isinstance(entries, dict):              # A feed with one entry is not a list.
            entries = [entries]
        found = 0
        for entry in entries:
            if 'im:rating' not in entry:
                continue                            # The first entry can be the app itself.
            out.append({
                'rating': int(entry['im:rating']['label']),
                'title': entry.get('title', {}).get('label', ''),
                'body': entry.get('content', {}).get('label', ''),
                'version': entry.get('im:version', {}).get('label', ''),
                'date': (entry.get('updated', {}).get('label', '') or '')[:10],
                'author': entry.get('author', {}).get('name', {}).get('label', ''),
                'country': country,
            })
            found += 1
        if not found:
            break
    return out
