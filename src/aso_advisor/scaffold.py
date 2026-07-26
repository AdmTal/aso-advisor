"""`aso init`: make a new workspace.

The command writes a complete, commented workspace. The comments explain each
field, so the files also work as a tutorial. With `--app-id`, the command reads
the public data of your app and fills in what it can.
"""

import re
from pathlib import Path

from . import db, store_api
from .workspace import CONFIG_NAME, STRATEGY_NAME

ID_IN_URL = re.compile(r'/id(\d+)')

CONFIG_TEMPLATE = """\
# ASO Advisor — workspace configuration.
# Documentation: https://github.com/AdmTal/aso-advisor/tree/main/docs
version: 1

app:
  name: {name}
  bundle_id: {bundle_id}
  # The numeric identifier of your App Store page. It is the number after "id"
  # in the page URL. The live commands need it.
  track_id: {track_id}
  # The localization that you write first. The tool compares the other
  # localizations against it.
  primary_locale: {primary_locale}
  # The home storefront, as an iTunes country code.
  default_country: {default_country}

markets:
  # The storefronts that `aso rank` checks.
  rank_countries: [{default_country}]
  # The storefronts that `aso reviews` reads.
  review_countries: [{default_country}]
  # Optional. Audit only these storefront groups. Empty means all groups that
  # have metadata.
  storefront_groups: []
  # Optional. Replace the built-in cross-localization table if Apple changes it.
  # storefront_groups_override:
  #   US:
  #     name: United States
  #     locales: [en-US, es-MX]

assets:
  check: true
  check_dimensions: true
  check_video_duration: true
  max_screenshots: 10
  max_previews: 3
  # The locales that must have their own screenshots. Empty means the primary
  # locale only.
  required_locales: []
  # Add device sizes that the tool does not know yet.
  # device_sizes:
  #   iphone-6.9: [[1320, 2868]]

audit:
  # Rules to switch off, for example [TITLE_REDUNDANT, LOCALE].
  # The list of rules is in docs/rules.md.
  disable_rules: []

# App Store Connect. Only `aso pull`, `aso push`, and `aso push-assets` need
# this. Make a key in App Store Connect → Users and Access → Integrations, then
# run `aso auth` to test it. Environment variables win over the values here.
# NEVER put the key itself in this file, and never commit the .p8 file.
# asc:
#   key_id: ABCDE12345
#   issuer_id: 00000000-0000-0000-0000-000000000000
#   private_key_path: ~/.appstoreconnect/keys/AuthKey_ABCDE12345.p8
#   app_id: {track_id}   # defaults to app.track_id

# How long the tool keeps the answers of the public Apple endpoints, in hours.
cache_hours: 12
"""

STRATEGY_TEMPLATE = """\
# ASO Advisor — your strategy.
#
# This file holds your positioning. Everything here is plain data. Change it
# when your positioning changes. No other file needs an edit.
#
# The scores are relative value for YOUR app, from 0 to 10. They are not search
# volume. Use them to say which word you want more.

# ---------------------------------------------------------------------------
# Brand. A store title that starts with keywords does not always hold your
# brand name. A user who heard your name finds you only when every word of the
# name is indexed in one localization per storefront.
# ---------------------------------------------------------------------------
brand_phrases:
  - {brand}

# ---------------------------------------------------------------------------
# Single words that you want in your keyword pool. The audit tells you which
# ones no localization indexes yet, and proposes a keyword field that has them.
# ---------------------------------------------------------------------------
seed_keywords: []
#  - term: planner
#    score: 9
#    why: The main category word. Users type it alone.
#  - term: habit
#    score: 7
#    why: Completes "habit tracker" in the same localization.

# ---------------------------------------------------------------------------
# The long-tail phrases that you want to rank for. A phrase matches only when
# ONE localization holds every word of it. The audit shows a coverage matrix
# per storefront, and `aso rank` measures your real position for each phrase.
# ---------------------------------------------------------------------------
phrase_targets: []
#  - phrase: daily habit tracker
#    score: 9
#  - phrase: routine planner with reminders
#    score: 6

# Words that do not need their own slot for a phrase to match.
phrase_stopwords: [with, and, on, for, the, a, an, of, to, in, my, your, no, by]

# ---------------------------------------------------------------------------
# Words that waste characters. The store ignores them, indexes them free, or
# does not allow them.
# ---------------------------------------------------------------------------
low_value_terms: [app, apps, free, best, top, new, ios, iphone, ipad, download, apple]

# Trademarks of other companies. They bring traffic, but they are a rejection
# risk under App Review guideline 2.3.7. The audit reports them as a note, not
# as an error, so that the bet stays visible.
trademark_terms: []
# Names of platform features. The risk is lower.
soft_trademark_terms: []

# ---------------------------------------------------------------------------
# Apple makes the discovery tags from your description. The audit checks that
# the first paragraphs hold these words.
# ---------------------------------------------------------------------------
ai_tag_terms: []
#  - habit
#  - planner

# ---------------------------------------------------------------------------
# The competitors that `aso competitors` watches. A title change by one of
# them is the best early signal that the keyword market moved.
# To find the identifiers, run:  aso competitors --suggest "your category"
# ---------------------------------------------------------------------------
competitors: []
#  - track_id: 123456789
#    label: The App That Owns The Category

# ---------------------------------------------------------------------------
# The root terms that `aso discover` expands through the autocomplete of the
# App Store. Apple sorts the suggestions by popularity.
# ---------------------------------------------------------------------------
discovery_seeds: []
#  - habit tracker
#  - daily planner

# Root terms in the local language, per storefront. English roots cannot tell
# you whether a market searches your category in its own language. These can,
# and the answer is often "no". A seed that returns nothing is a finding.
local_discovery_seeds: {{}}
#  de: [gewohnheiten, tagesplaner]

# ---------------------------------------------------------------------------
# Locales with no metadata that you want to add, and why. The audit repeats
# them until you add them.
# ---------------------------------------------------------------------------
locale_priority: {{}}
#  de-DE: Germany — large market, cheap translation

# ---------------------------------------------------------------------------
# Trade-offs that you took on purpose. The audit shows them in every run, so
# that they stay conscious decisions and not forgotten accidents.
# ---------------------------------------------------------------------------
notes: []
#  - key: es-mx-english-slot
#    title: es-MX carries English keywords for the US storefront
#    detail: >
#      The cost is that Mexico indexes no Spanish terms. Revisit this when
#      Mexico revenue matters.

# ---------------------------------------------------------------------------
# The `aso verify-groups` probe. The command searches "<unique keyword>
# <anchor>" and checks that your app appears. The controls are words that you
# index nowhere; they must NOT return your app.
# ---------------------------------------------------------------------------
probe:
  anchor: ''
  controls: []
"""

TITLES_TEMPLATE = """\
# Titles, subtitles, and keyword fields, one block per App Store locale.
#
# Limits: name 30 characters, subtitle 30 characters, keywords 100 characters.
# The keyword field is comma-separated with NO spaces. Single words only: the
# store makes the phrases itself.
#
# `language:` is a note for the reader. A field that ends with `_eng` is a
# back-translation for review. The tool ignores both.

locales:
  {primary_locale}:
    language: {language}
    name: {name}
    subtitle: ''
    keywords: ''
"""

DESCRIPTIONS_TEMPLATE = """\
# Descriptions, promotional text, and release notes, one block per locale.
#
# Limits: description 4000 characters, promotional_text 170 characters,
# whats_new 4000 characters.
#
# The description does not feed keyword rank. It feeds the discovery tags of
# Apple and the assistants that recommend apps. Say plainly what the app does
# in the first paragraph.
#
# You can change promotional_text WITHOUT a new release. It is the best place
# for a conversion test.

locales:
  {primary_locale}:
    language: {language}
    description: |-
      {description}
    promotional_text: ''
    whats_new: ''
"""

WORKSPACE_README = """\
# ASO workspace

This directory holds the App Store metadata of this project, its history, and
the strategy behind it. The [ASO Advisor](https://github.com/AdmTal/aso-advisor)
reads it.

```
aso/
├── aso.yaml        # app identity and market settings
├── strategy.yaml   # keywords, phrases, competitors — the strategy
├── versions/       # one directory per metadata version
│   └── {version}/
│       ├── titles_and_keywords.yaml
│       ├── descriptions.yaml
│       └── assets/<locale>/screenshots/<device>/01-*.png
├── reports/        # generated reports (not in version control)
└── state/          # SQLite state (not in version control)
```

## Daily use

```bash
aso pull           # read the live metadata from App Store Connect
aso audit          # audit the newest version and write a report
aso list           # the open suggestions
aso show S-1a2b3c4d
aso dismiss S-1a2b3c4d "we accept this trade-off"
aso push --dry-run # show what a push would change
aso push           # send the metadata back
aso push-assets    # upload the screenshots and the preview videos
```

`pull`, `push`, and `push-assets` need an App Store Connect key. Run
`aso auth` for the steps.

## Rules for this directory

- Put `versions/` and the two YAML files in version control. They are the
  record of what you published.
- Do not put `reports/` and `state/` in version control. Both are generated.
- One directory per version. Copy the last one and edit the copy. Never edit a
  version that is live.
- Keep the localized screenshots next to the metadata that they belong to.
"""

GITIGNORE = """\
# Generated by the ASO Advisor. Both directories are safe to delete.
state/
reports/

# Credentials. An App Store Connect key must never enter version control.
.env
*.p8
"""


def parse_app_id(value):
    """Take the numeric identifier out of a number or an App Store URL."""
    if not value:
        return 0
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    match = ID_IN_URL.search(text)
    return int(match.group(1)) if match else 0


def fetch_identity(track_id=0, bundle_id='', country='us'):
    """Read the public data of an app. Returns a dictionary, empty on failure."""
    conn = db.connect_memory()
    try:
        if bundle_id:
            results = store_api.lookup(conn, bundle_id=bundle_id, country=country)
        else:
            results = store_api.lookup(conn, track_ids=[track_id], country=country)
    except store_api.StoreAPIError:
        return {}
    finally:
        conn.close()
    if not results:
        return {}
    app = results[0]
    return {
        'track_id': app.get('trackId') or 0,
        'bundle_id': app.get('bundleId') or '',
        'name': app.get('trackName') or '',
        'description': app.get('description') or '',
        'version': str(app.get('version') or '1.0'),
        'seller': app.get('sellerName') or '',
        'url': app.get('trackViewUrl') or '',
    }


def _first_paragraph(text, limit=300):
    paragraph = (text or '').strip().split('\n\n')[0].strip()
    if len(paragraph) > limit:
        paragraph = paragraph[:limit].rsplit(' ', 1)[0] + ' …'
    return paragraph or 'Say here, in plain words, what the app does.'


def create(root, identity=None, primary_locale='en-US', country='us', version=None,
           force=False):
    """Write a new workspace. Returns the list of files that it wrote."""
    root = Path(root)
    identity = identity or {}
    if (root / CONFIG_NAME).exists() and not force:
        raise FileExistsError(f'{root / CONFIG_NAME} exists. Use --force to overwrite it.')

    version = version or identity.get('version') or '1.0'
    name = identity.get('name', '')
    brand = (name.split(':')[0].split('-')[0].strip() or 'Your Brand Name').lower()

    version_dir = root / 'versions' / version
    (version_dir / 'assets' / primary_locale / 'screenshots').mkdir(parents=True, exist_ok=True)
    (version_dir / 'assets' / primary_locale / 'previews').mkdir(parents=True, exist_ok=True)
    (root / 'reports').mkdir(parents=True, exist_ok=True)

    files = {
        root / CONFIG_NAME: CONFIG_TEMPLATE.format(
            name=name or 'Your App',
            bundle_id=identity.get('bundle_id', '') or 'com.example.app',
            track_id=identity.get('track_id', 0) or 0,
            primary_locale=primary_locale,
            default_country=country),
        root / STRATEGY_NAME: STRATEGY_TEMPLATE.format(brand=brand),
        version_dir / 'titles_and_keywords.yaml': TITLES_TEMPLATE.format(
            primary_locale=primary_locale,
            language=primary_locale,
            name=name or 'Your App'),
        version_dir / 'descriptions.yaml': DESCRIPTIONS_TEMPLATE.format(
            primary_locale=primary_locale,
            language=primary_locale,
            description=_first_paragraph(identity.get('description', ''))),
        root / 'README.md': WORKSPACE_README.format(version=version),
        root / '.gitignore': GITIGNORE,
    }
    written = []
    for path, content in files.items():
        if path.exists() and not force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        written.append(path)
    return written
