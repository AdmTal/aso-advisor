# The workspace

A workspace is one directory that holds the App Store metadata of a project,
its history, its assets, and the strategy behind it. Put one in each project
that ships an app. The advisor is a utility that you install one time; the
workspace is the part that belongs to the project.

- [Layout](#layout)
- [How the tool finds the workspace](#how-the-tool-finds-the-workspace)
- [`aso.yaml`](#asoyaml)
- [`strategy.yaml`](#strategyyaml)
- [Metadata YAML](#metadata-yaml)
- [Versions](#versions)
- [Assets: localized screenshots and app previews](#assets-localized-screenshots-and-app-previews)
- [Generated directories](#generated-directories)
- [What to put in version control](#what-to-put-in-version-control)

---

## Layout

```
aso/
├── aso.yaml                            # app identity, markets, asset settings
├── strategy.yaml                       # brand, keywords, phrases, competitors
├── README.md                           # written by `aso init`, for your team
├── .gitignore                          # written by `aso init`
├── versions/
│   ├── 2.0/
│   │   └── titles_and_keywords.yaml
│   └── 2.1/
│       ├── titles_and_keywords.yaml
│       ├── descriptions.yaml
│       └── assets/
│           ├── en-US/
│           │   ├── screenshots/iphone-6.9/01-hero.png
│           │   └── previews/iphone-6.9/01-demo.mp4
│           └── de-DE/
│               └── screenshots/iphone-6.9/01-start.png
├── reports/                            # generated
└── state/aso.sqlite3                   # generated
```

Only two things are necessary: the file `aso.yaml`, and one directory under
`versions/` with one YAML file in it. Everything else is optional.

The default name of the directory is `aso/`. You can use another name, and then
you pass `--workspace` or you set `ASO_WORKSPACE`.

---

## How the tool finds the workspace

The tool looks in this order:

1. the `--workspace PATH` option;
2. the `ASO_WORKSPACE` environment variable;
3. an `aso/` directory in the current directory or in a parent directory;
4. an `aso.yaml` file in the current directory or in a parent directory.

The search goes upwards, in the same way as git. You can therefore run `aso
audit` from anywhere inside your project.

For `--workspace` and `ASO_WORKSPACE` you can name the workspace directory
itself or its parent. Both of these work:

```bash
aso --workspace ~/projects/my-app audit
aso --workspace ~/projects/my-app/aso audit
```

`aso where` prints every path that the tool resolved.

---

## `aso.yaml`

Everything in this file is optional. The values below are the defaults.

```yaml
version: 1

app:
  name: Trailwise                # used in the report header
  bundle_id: com.example.app     # information only
  track_id: 123456789            # the numeric App Store identifier
  primary_locale: en-US          # the localization that you write first
  default_country: us            # your home storefront (iTunes country code)

markets:
  rank_countries: [us]           # the storefronts that `aso rank` checks
  review_countries: [us]         # the storefronts that `aso reviews` reads
  storefront_groups: []          # audit only these groups; empty means all
  storefront_groups_override: {} # replace an entry of the built-in table

assets:
  check: true                    # audit the assets as part of `aso audit`
  check_dimensions: true         # read the pixel size of each image
  check_video_duration: true     # read the duration of each app preview
  max_screenshots: 10            # the limit of App Store Connect per set
  max_previews: 3                # the limit of App Store Connect per set
  required_locales: []           # locales that need their own screenshots
  device_sizes: {}               # extra device sizes, or your own names

audit:
  disable_rules: []              # rule identifiers to switch off

cache_hours: 12                  # how long to keep an answer from Apple
```

### `app.track_id`

The number after `id` in your App Store page URL. The live commands (`rank`,
`competitors`, `reviews`, `verify-groups`) need it. The audit does not.

You can also find it from the bundle identifier:

```bash
aso lookup --bundle-id com.example.app
```

### `app.primary_locale`

The audit uses it in three places: as the source for the description-depth
comparison, as the locale of the description that feeds the discovery tags, and
as the default locale that needs screenshots.

### `markets.storefront_groups`

The built-in table has more than 30 storefronts. If you sell in six, name them,
and the phrase coverage matrix stays readable:

```yaml
markets:
  storefront_groups: [US, GB, DE, FR, JP, BR]
```

### `markets.storefront_groups_override`

Apple does not publish the cross-localization table, and it changes it from
time to time. Test a group with `aso verify-groups`. If the result does not
match the built-in table, correct it here:

```yaml
markets:
  storefront_groups_override:
    US:
      name: United States
      locales: [en-US, es-MX, ru, ar-SA, vi]
```

### `assets.device_sizes`

The tool knows the common device sets. Add a size that it does not know, or use
your own directory names:

```yaml
assets:
  device_sizes:
    iphone-6.9: [[1320, 2868], [1290, 2796]]
    my-tablet: [[2048, 2732]]
```

### `audit.disable_rules`

Every rule identifier is in [rules.md](rules.md), and `aso rules` prints the
list. Switch off the rules that do not fit your app:

```yaml
audit:
  disable_rules: [LOCALE, TITLE_REDUNDANT, ASSET_ORDER]
```

To hide one finding, and not the whole rule, use `aso dismiss` instead.

---

## `strategy.yaml`

This file holds your positioning. It is plain data. The audit reads it; nothing
else needs an edit when your positioning changes.

| Field | Type | What it does |
| --- | --- | --- |
| `brand_phrases` | list of text | The names that users type when they know you. The BRAND rule checks that every word of a phrase is indexed in one localization per storefront. |
| `seed_keywords` | scored list | The single words that you want. The SEED rule reports the ones that no localization indexes. The report proposes a keyword field that holds them. |
| `phrase_targets` | scored list | The queries that you want to win. The PHRASE rule and the coverage matrix use them, and `aso rank` measures them. |
| `phrase_stopwords` | list of text | Words that do not need a slot for a phrase to match. |
| `low_value_terms` | list of text | Words that waste characters. The LOWVALUE rule reports them. |
| `trademark_terms` | list of text | Trademarks of other companies. Reported as INFO, because they are a review risk that you accept on purpose. |
| `soft_trademark_terms` | list of text | Names of platform features. Lower risk. |
| `ai_tag_terms` | list of text | The core category words that your description opening needs. |
| `competitors` | map or list | The apps that `aso competitors` watches. |
| `discovery_seeds` | list of text | The roots that `aso discover` expands through the autocomplete. |
| `local_discovery_seeds` | map | Roots in the local language, per country code. |
| `locale_priority` | map | Locales with no metadata that you want, and why. |
| `notes` | list | Trade-offs that you took on purpose. Shown as INFO in every run. |
| `probe` | map | The anchor and the control words of `aso verify-groups`. |

### The shapes that a scored list accepts

All three of these are valid:

```yaml
seed_keywords: [offline, elevation]                # score 5 for each

seed_keywords:
  - [offline, 8]

seed_keywords:
  - term: offline
    score: 8
    why: The main reason that users choose this app.
```

The third shape is the best one. The `why` text appears in the suggestion, so
the next person understands the decision.

### Competitors

Two shapes are valid:

```yaml
competitors:
  123456789: Rival Maps

competitors:
  - track_id: 123456789
    label: Rival Maps
```

### Notes

A note is a decision that you want to see in every run, so that it stays a
decision and does not become an accident:

```yaml
notes:
  - key: es-mx-english-slot
    title: es-MX carries English keywords for the United States storefront
    detail: >
      Mexico therefore indexes no Spanish word. Revisit this when Mexico
      revenue matters.
```

---

## Metadata YAML

`aso pull` writes these files for you, and `aso push` sends them back. You can
also write them by hand, or generate them from another tool.

Each version directory holds one or more YAML files. The loader reads every
`*.yaml` and `*.yml` file and merges the `locales:` block of each one. A file
without a `locales:` block is ignored, so you can keep your own notes in the
same directory.

```yaml
locales:
  en-US:
    language: English (United States)   # a note for the reader, ignored
    name: 'Trailwise: Hike & Trail GPS' # 30 characters
    subtitle: Offline Maps for Hiking   # 30 characters
    keywords: |-                        # 100 characters
      map,elevation,tracker,route,walk,trek,compass
    description: |-                     # 4000 characters
      The first paragraph says what the app does.
    promotional_text: 170 characters, changeable without a release.
    whats_new: |-                       # 4000 characters
      What is new in this version.
```

| Key | Alias | Limit |
| --- | --- | --- |
| `name` | `title` | 30 |
| `subtitle` | | 30 |
| `keywords` | | 100 |
| `description` | | 4000 |
| `promotional_text` | `promo_text` | 170 |
| `whats_new` | `release_notes` | 4000 |

Two kinds of key are ignored on purpose:

- `language:` — the plain name of the locale, for the human reader.
- any key that ends with `_eng` — a back-translation for review, for example
  `name_eng` or `keywords_eng`. Keep them next to the localized value. They
  make a review of a language that you do not read possible.

```yaml
  de-DE:
    language: German
    name: 'Trailwise: Wandern & Karten'
    name_eng: 'Trailwise: Hiking and Maps'
```

The locale code must be a code that App Store Connect accepts: `en-US`,
`en-GB`, `de-DE`, `pt-BR`, `zh-Hans`, and so on.

### In-app purchases

A version file can also hold an `in_app_purchases:` block. The display name of
a product is 30 characters that the store indexes, and the description adds 45
more:

```yaml
in_app_purchases:
  - product_id: com.example.pro
    reference_name: Pro unlock          # a note for you, not indexed
    locales:
      en-US:
        name: Offline Park Packs        # 30 characters, indexed
        description: Download a park and walk with no signal.   # 45 characters
```

The audit checks the lengths, tells you when a name only repeats words that you
already index, and reports the locales where a product has no translation. The
tool does not push in-app purchases; change them in App Store Connect.

---

## Versions

One directory per metadata version. The name is free text; the tool sorts by
the numbers in the name, so `2.10` comes after `2.9`.

```
versions/2.0/    versions/2.1/    versions/3.0/
```

Keep the old versions. They give you three things:

- `aso diff` and the DIFF rule, so every metadata push has a record;
- `aso audit --metadata-version 2.0`, to audit what is live while you write the
  next version;
- a history that explains a rank change months later.

The workflow of a release: copy the newest directory, give the copy the name of
the new version, and edit the copy. Never edit a directory that is live.

```bash
cp -r aso/versions/2.1 aso/versions/2.2
```

---

## Assets: localized screenshots and app previews

Screenshots belong to a version and to a locale, exactly like the text. Keep
them together:

```
versions/2.1/assets/
├── en-US/
│   ├── screenshots/
│   │   ├── iphone-6.9/
│   │   │   ├── 01-offline-map.png
│   │   │   ├── 02-elevation.png
│   │   │   └── 03-waypoints.png
│   │   └── ipad-13/
│   │       └── 01-offline-map.png
│   └── previews/
│       └── iphone-6.9/
│           └── 01-hero.mp4
└── de-DE/
    └── screenshots/iphone-6.9/01-karte.png
```

The rules of the tree:

1. The first level is the locale code. It must match a locale of the metadata.
2. The second level is `screenshots/` or `previews/`.
3. The third level is the device set.
4. The file name gives the display order. Use a numeric prefix.

The device names that the tool knows:

| Name | Accepted sizes (portrait) |
| --- | --- |
| `iphone-6.9` | 1320×2868, 1290×2796 |
| `iphone-6.7` | 1290×2796, 1284×2778 |
| `iphone-6.5` | 1242×2688, 1284×2778 |
| `iphone-6.1` | 1179×2556, 1170×2532 |
| `iphone-5.5` | 1242×2208 |
| `ipad-13` | 2064×2752, 2048×2732 |
| `ipad-12.9` | 2048×2732 |
| `ipad-11` | 1668×2388, 1640×2360 |
| `mac` | 1280×800, 1440×900, 2560×1600, 2880×1800 |

A landscape image is the same pair, reversed. Apple changes these lists, so the
tool treats a wrong size as a warning, not as a fact. Add or replace a size
with `assets.device_sizes`, or switch the check off with
`assets.check_dimensions: false`.

The asset audit reads the file headers only. It uses the standard library, and
it never opens the network. It reports:

- a screenshot with an unexpected pixel size;
- a screenshot with an alpha channel (App Store Connect refuses it);
- a set with more files than the store accepts;
- an app preview that is not 15 to 30 seconds long;
- file names that do not show the display order;
- a locale of the metadata that has no screenshots;
- an assets directory that has no metadata locale.

```bash
aso assets                       # the tree and the findings, alone
aso audit --no-assets            # skip the asset rules in an audit
aso push-assets --dry-run        # what an upload would change
aso push-assets                  # upload the sets that changed
```

`aso push-assets` uploads this tree to App Store Connect. It compares the
checksum of each file with the checksum that the store holds, so it uploads
only the sets that changed. It can also read a tree that lives outside the
workspace, for example the export folder of a design tool. See
[app-store-connect.md](app-store-connect.md).

### Captions

The store indexes the text in your screenshot captions, and no tool can read
the text inside an image. Write the captions in `assets/captions.yaml`:

```yaml
locales:
  en-US:
    - Offline maps for the whole park
    - See every metre of climb before you go
  de-DE:
    iphone-6.9:                       # a list per device, when they differ
      - Offline-Karten für den ganzen Park
```

One line per screenshot, in the display order. The audit then checks that the
captions hold words of your target phrases, that they are short enough to read
in one second, and that their number matches the number of screenshots. The
rules stay quiet until the file exists.

---

## Generated directories

| Directory | Content | Safe to delete |
| --- | --- | --- |
| `reports/` | One Markdown file per audit, named `aso-report-<unix timestamp>.md`. | Yes |
| `state/` | `aso.sqlite3`: the suggestions, the runs, the rank history, the competitor snapshots, and the cache of the Apple answers. | Yes, but you lose the memory |

If you delete the database, the next audit reports every suggestion as new, and
your dismissals are gone. Keep it on your machine. It holds no credentials.

---

## What to put in version control

**Commit:**

- `aso.yaml` and `strategy.yaml`;
- everything under `versions/`, the YAML and the assets;
- the `README.md` that `aso init` wrote.

**Do not commit:**

- `reports/`;
- `state/`;
- `.env`;
- any `*.p8` file. An App Store Connect key must never enter version control.

`aso init` writes an `.gitignore` in the workspace with all four entries.

The screenshots make the repository larger. If that is a problem, use
[Git LFS](https://git-lfs.com/) for `aso/versions/**/assets/**`, or keep the
assets in a separate repository and make `assets` a symbolic link. The tool
follows a symbolic link.
