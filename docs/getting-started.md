# Getting started

This guide takes you from an empty project to your first metadata fix. It needs
about 30 minutes. You need Python 3.9 or later and an app on the App Store.

The guide has seven steps:

1. [Install the tool](#1-install-the-tool)
2. [Look at the example first](#2-look-at-the-example-first)
3. [Make your workspace](#3-make-your-workspace)
4. [Put your live metadata into the workspace](#4-put-your-live-metadata-into-the-workspace)
5. [Run the first audit](#5-run-the-first-audit)
6. [Write your strategy](#6-write-your-strategy)
7. [Make the changes and close the loop](#7-make-the-changes-and-close-the-loop)

---

## 1. Install the tool

```bash
pipx install aso-advisor
aso --version
```

`pipx` puts the tool in its own environment and gives you the `aso` command
everywhere. If you do not have pipx, `pip install aso-advisor` also works.

The tool has one dependency, PyYAML. Everything else comes from the standard
library.

---

## 2. Look at the example first

The repository has a complete workspace for an app that does not exist. It has
real problems in it, so the audit has something to find.

```bash
git clone https://github.com/AdmTal/aso-advisor.git
cd aso-advisor
aso --workspace examples/trailwise audit --no-state --no-report
```

Read the action list. Then open
[`examples/trailwise/`](../examples/trailwise) and compare the findings with
the YAML files. The example shows the shape of a good workspace.

The two options keep the example clean:

- `--no-state` does not write a database.
- `--no-report` does not write a report file.

---

## 3. Make your workspace

Go to the repository of your app. Find the numeric identifier of your App
Store page: it is the number after `id` in the page URL.

```
https://apps.apple.com/us/app/your-app/id123456789
                                        ^^^^^^^^^
```

```bash
cd ~/projects/my-app
aso init --app-id 123456789
```

The command reads the public data of your app and writes:

```
aso/
├── aso.yaml                  # app identity and market settings
├── strategy.yaml             # empty, with comments that explain each field
├── README.md                 # a short guide for your teammates
├── .gitignore                # keeps reports/ and state/ out of git
└── versions/<your version>/
    ├── titles_and_keywords.yaml
    ├── descriptions.yaml
    └── assets/<locale>/screenshots/
```

Look at `aso/aso.yaml` and check three fields:

```yaml
app:
  track_id: 123456789      # the number from the URL
  primary_locale: en-US    # the localization that you write first
  default_country: us      # your home storefront
```

If your app is not on the store yet, run `aso init` without `--app-id` and fill
in the fields by hand.

---

## 4. Put your live metadata into the workspace

The advisor audits what you give it, so the audit is only correct when the YAML
matches the store. You have three ways to fill it.

### With `aso pull` (the fastest way)

If you have an App Store Connect API key, one command fills the workspace:

```bash
pipx install 'aso-advisor[sync]'
aso auth          # it prints the steps when you have no key yet
aso pull
```

`aso pull` reads the live metadata of every locale and writes it into
`aso/versions/<the live version>/`. Read
[app-store-connect.md](app-store-connect.md) for the key.

Later, the same key lets you publish from the workspace with `aso push` and
`aso push-assets`, so the whole loop lives in your repository.

### By hand (10 minutes, and you learn the layout)

Open App Store Connect and copy the values into
`aso/versions/<version>/titles_and_keywords.yaml`. One block per locale:

```yaml
locales:
  en-US:
    language: English (United States)
    name: 'Trailwise: Hike & Trail GPS'      # 30 characters maximum
    subtitle: Offline Maps for Backpacking   # 30 characters maximum
    keywords: |-
      map,elevation,tracker,route,walk,trek,compass,summit
  de-DE:
    language: German
    name: 'Trailwise: Wandern & Karten'
    subtitle: Offline Wanderkarten & GPS
    keywords: |-
      route,berg,gipfel,kompass,tour,pfad,steig,alpen
```

Rules for the keyword field:

- Single words, separated by commas, with **no space** after the comma.
- Do not repeat a word from the name or the subtitle. The store already indexes
  those words, with more weight.
- The store makes the phrases itself, so `offline maps` as one entry only
  wastes a character.

Put the long text in `descriptions.yaml`:

```yaml
locales:
  en-US:
    description: |-
      The first paragraph says plainly what the app does.

      More paragraphs, then the feature list.
    promotional_text: 170 characters that you can change without a release.
    whats_new: What is new in this version.
```

### With fastlane

If you already use `fastlane deliver`, one command converts the tree:

```bash
aso import --fastlane fastlane/metadata --metadata-version 2.1
```

The command reads one directory per locale and one text file per field, and it
writes the YAML of the workspace. Your fastlane tree does not change, and
nothing is uploaded.

### With the App Store Connect API

If you write your own sync script with the
[App Store Connect API](https://developer.apple.com/documentation/appstoreconnectapi),
make it write the same YAML shape. The advisor reads every `*.yaml` file in the
version directory and merges the `locales:` blocks, so your script can use any
file names.

### Old versions are valuable

If you have the metadata of your last releases, add one directory per release:
`versions/2.0/`, `versions/2.1/`. The advisor then reports what changed between
two versions, and you get a record of every metadata push.

---

## 5. Run the first audit

```bash
aso audit
```

The first run finds a lot. This is normal. The output has three parts.

**The counters.** `open` is the number of suggestions that need a decision.
`new`, `regressed`, and `resolved` compare this run with the run before.

**The action list**, in the order of severity:

| Severity | Meaning | What to do |
| --- | --- | --- |
| 🟥 CRITICAL | App Store Connect refuses the upload. | Fix it now. |
| 🟧 HIGH | You lose indexing or you waste characters. | Fix it in this release. |
| 🟨 MEDIUM | A real opportunity. | Take the ones that fit your strategy. |
| ⬜ LOW | Small gains and polish. | Take them when you have time. |
| ℹ️ INFO | A record, or a bet that you took. | Read it. Do nothing. |

**The report file**, in `aso/reports/aso-report-<timestamp>.md`. The report has
everything from the terminal, plus the phrase coverage matrix, the proposed
keyword fields, and the last live rank snapshot. The name holds a Unix
timestamp, so two runs never overwrite each other.

### Triage the list

Work with three commands:

```bash
aso list                          # everything that is open
aso show S-1a2b3c4d               # the full reason and the fix
aso dismiss S-1a2b3c4d "reason"   # I disagree, stay quiet about it
```

Dismiss without guilt. A dismissed suggestion never comes back, and the reason
that you wrote stays in the database. It becomes the record of the decision.

If a whole rule does not fit your app, switch it off in `aso.yaml`:

```yaml
audit:
  disable_rules: [LOCALE, TITLE_REDUNDANT]
```

---

## 6. Write your strategy

The audit gets much stronger when it knows what you want. Open
`aso/strategy.yaml`. Four fields do most of the work.

**`brand_phrases`** — the name that users type when they heard of you. A store
title that starts with keywords often does not hold the brand name, and then
your best traffic cannot find you.

```yaml
brand_phrases:
  - trailwise
```

**`seed_keywords`** — the single words that you want in your keyword pool, with
your own score from 0 to 10. The audit reports the words that no localization
indexes, and it proposes a new keyword field that holds them.

```yaml
seed_keywords:
  - term: offline
    score: 8
    why: The main reason that users choose this app.
```

**`phrase_targets`** — the queries that you want to win. A phrase matches only
when ONE localization holds every word of it, so this list produces the most
valuable findings of the whole tool.

```yaml
phrase_targets:
  - phrase: offline hiking maps
    score: 9
```

You do not have to invent this list. Ask the store:

```bash
aso phrases            # proposals from the autocomplete and your competitors
aso phrases --write    # add the strong ones to strategy.yaml
```

[keyword-research.md](keyword-research.md) explains the method and the scores.

**`competitors`** — the apps to watch. To find the identifiers, ask the store:

```bash
aso competitors --suggest "hiking gps"
```

Copy the identifiers of the apps that really compete with you.

Run `aso audit` again. The list is now about your strategy, not only about your
formatting.

---

## 7. Make the changes and close the loop

Edit the YAML in the version directory, publish the change with your normal
process, then run the audit again:

```bash
aso audit
```

The output now shows the value of the memory:

```
 open: 9   new: 2   regressed: 0   resolved: 4

 ✅ RESOLVED since the run before:
    - en-US: the keyword field has spaces next to commas
```

A suggestion that you fixed resolves by itself. A problem that comes back is
marked `[REGRESSED]`. A suggestion that you dismissed stays quiet.

```bash
aso history      # the open count of each run, over time
```

### Add the live data

When your metadata is in order, look at the store:

```bash
aso rank          # your real position for each target phrase
aso discover      # what users type, in the popularity order of Apple
aso reviews       # the words that your users write, and your rating pulse
aso competitors   # what the other apps changed this week
```

Each command explains its own output. Read
[docs/workflows.md](workflows.md) for the loops that put them together, and
[docs/commands.md](commands.md) for every option.

---

## What next

- [Keyword research](keyword-research.md) — where the target phrases come
  from, and how `aso phrases` builds the first list.
- [App Store Connect](app-store-connect.md) — make an API key, then pull,
  push, and upload the screenshots from the workspace.
- [Workflows](workflows.md) — the weekly loop, the release ritual, a keyword
  research sprint, CI, many apps, and how to use an AI assistant with the
  reports.
- [Concepts](concepts.md) — why the rules say what they say. Read this before
  you disagree with a suggestion.
- [The workspace](workspace.md) — every configuration field, and the asset
  tree for localized screenshots and app previews.
