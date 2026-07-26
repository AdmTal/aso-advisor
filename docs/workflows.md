# Workflows

The tool is a set of small commands. This page shows the loops that people
build from them. Take the ones that fit your team, and ignore the rest.

1. [The first week](#1-the-first-week)
2. [The release ritual](#2-the-release-ritual)
3. [The weekly market watch](#3-the-weekly-market-watch)
4. [A keyword research sprint](#4-a-keyword-research-sprint)
5. [Enter a new market](#5-enter-a-new-market)
6. [The guard in your build pipeline](#6-the-guard-in-your-build-pipeline)
7. [Many apps, one machine](#7-many-apps-one-machine)
8. [Work with an AI assistant](#8-work-with-an-ai-assistant)
9. [A team, and the record of the decisions](#9-a-team-and-the-record-of-the-decisions)
10. [A quarterly health check](#10-a-quarterly-health-check)

---

## 1. The first week

**Goal:** the audit list becomes short and honest, and every open item is a real
decision.

**Day 1 — set it up and take the free wins.**

```bash
aso init --app-id 123456789
# put your live metadata into aso/versions/<version>/
aso audit
```

Fix everything that is CRITICAL and HIGH. Most of them are pure waste:
duplicates, spaces, and empty fields. You do not need a strategy for this part.

**Day 2 — write the strategy.**

Open `aso/strategy.yaml`. Write `brand_phrases`, five to ten `seed_keywords`,
and five `phrase_targets`. Run `aso audit` again. The list is now about your
positioning.

**Day 3 — ask the store.**

```bash
aso discover                  # what do users actually type
aso reviews                   # what words do your users write
aso competitors --suggest "your main category phrase"
```

Move the good words into `strategy.yaml`. Run the audit again.

**Day 4 — decide.**

```bash
aso list
aso show S-1a2b3c4d
aso dismiss S-1a2b3c4d "we do not want this audience"
```

Every remaining item must be an item that you plan to do. If it is not, dismiss
it with the reason. A short list is a list that you read.

**Day 5 — publish and close the loop.**

Push the metadata with your normal process, then run `aso audit`. The fixed
items resolve by themselves, and `aso rank` starts its history.

---

## 2. The release ritual

Run this before every metadata push. It takes two minutes and it catches the
failures that App Store Connect finds an hour later.

```bash
cp -r aso/versions/2.1 aso/versions/2.2     # never edit a version that is live
# edit aso/versions/2.2/
aso audit --metadata-version 2.2
aso diff --old 2.1 --new 2.2                # read the change out loud
aso assets --metadata-version 2.2           # sizes, alpha, counts, order
```

Three questions before you push:

1. Is anything CRITICAL? Then the upload fails.
2. Does `aso diff` show only the changes that you meant to make?
3. Did a fix create a new problem? A new word in a title often creates a new
   `DUP_TITLE` in a keyword field.

After the push, run `aso audit` one more time on the new version. That run is
the record: it resolves what you fixed, and the DIFF note documents the push.

---

## 3. The weekly market watch

Fifteen minutes, once a week. It is the loop that finds a change before it
becomes a problem.

```bash
aso rank            # did we move?
aso competitors     # did they move?
aso reviews         # what do users say and what words do they use?
```

Read the output in that order and ask:

- **A term that dropped by 10 or more.** Did a competitor change a title? Did
  you change that keyword field two weeks ago?
- **A competitor with a new title.** This is the strongest signal in the tool.
  A serious competitor changes a title only after research. Take the words that
  they added and put them into `aso discover`.
- **Rating velocity.** Ratings per day is the best free measure of install
  volume. If a rival doubles it, look at what they shipped.
- **The 30-day rating average below your overall average.** Fix the reason
  before you buy traffic. Rating recency is a ranking input.

Note what you decide in the commit message of `strategy.yaml`. In three months,
that message is the only record of why the keyword field changed.

---

## 4. A keyword research sprint

Half a day, twice a year, or after a large feature.

**Step 1 — collect the raw words.**

```bash
aso discover --deep > /tmp/ideas.txt
aso discover --country gb --deep >> /tmp/ideas.txt
aso reviews --pages 5 >> /tmp/ideas.txt
```

`discover` gives the queries that users type, in the popularity order of Apple.
`reviews` gives the words that your own users write. The two lists rarely
match, and the difference is the interesting part.

**Step 2 — score them by hand.**

Put the good ones into `strategy.yaml` as `seed_keywords` with your own score,
and the good queries as `phrase_targets`. Write the `why` text. Your future
self needs it.

**Step 3 — let the tool do the arithmetic.**

```bash
aso audit
```

The report proposes a complete new keyword field per localization: it fills the
free characters with your best uncovered seeds, then it exchanges the weakest
terms. It never removes a word that a target phrase needs, and it never removes
a trademark that you accepted on purpose.

```diff
- map,elevation,tracker,route,walk,trek,compass,summit,waypoint,park
+ map,elevation,tracker,route,walk,trek,compass,summit,waypoint,park,planner,walking,gpx
```

Read the proposal. It is a start, not an answer.

**Step 4 — measure.**

Push, wait two weeks, then run `aso rank`. Two weeks is the minimum. A keyword
change needs time to enter the index and more time to collect the behaviour
signals that decide the position.

---

## 5. Enter a new market

Before you pay a translator, ask whether the market searches your category in
its own language.

```bash
# Add local-language roots to strategy.yaml:
#   local_discovery_seeds:
#     cz: [nahrávání obrazovky, záznam obrazovky, obrazovka]
aso discover --country cz
```

Three answers are possible:

- **Rich local completions.** The market searches in its own language.
  Translate the metadata, and use the completions as the keyword field.
- **Nothing at all, but the English roots complete richly.** The market searches
  in English. Translate the name, the subtitle, and the description for
  conversion, and keep the keyword field in the language that users type.
- **Nothing at all, in both languages.** The category has no demand there. Move
  the effort to another market.

The third answer saves the most money, and only a live check can give it.

When the localization exists, check that it really indexes where you think:

```bash
aso verify-groups --group CZ
```

---

## 6. The guard in your build pipeline

A field that is too long must fail the pull request, not the upload.

```yaml
# .github/workflows/aso-audit.yml
name: ASO audit
on:
  pull_request:
    paths: ['aso/**']

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install aso-advisor
      - run: aso audit --fail-on critical --no-state --no-report
```

The complete file, with a job that writes the report into the pull request as a
comment, is in
[`examples/github-actions/aso-audit.yml`](../examples/github-actions/aso-audit.yml).

Notes:

- `--no-state` keeps the database out of the pipeline. The state belongs to a
  person, not to a runner.
- Start with `--fail-on critical`. Move to `high` when your list is clean.
- Add a pre-commit hook if you prefer a fast local check:
  `aso audit --fail-on critical --no-state --no-report`.

---

## 7. Many apps, one machine

An agency or a studio has one workspace per app and one command that walks over
all of them.

```bash
for app in ~/projects/*/; do
  [ -d "$app/aso" ] || continue
  echo "== $(basename "$app")"
  aso --workspace "$app" audit --fail-on high --no-report || true
done
```

Or with the environment variable, one app per shell:

```bash
export ASO_WORKSPACE=~/projects/trailwise/aso
aso audit && aso rank
```

Each workspace keeps its own state, its own history, and its own dismissals, so
the apps never mix.

---

## 8. Work with an AI assistant

The reports are Markdown and the audit speaks JSON, so an assistant can work
with them directly.

**Give the assistant the whole picture.**

```bash
aso audit --json > /tmp/audit.json
```

Then ask: "Here is my ASO audit and my strategy file. Write three subtitle
options for de-DE that cover the missing phrase words, keep 30 characters, and
do not repeat a word of the name."

The audit gives the constraints, and the assistant writes the words. That
division works better than a prompt without data.

**Let the assistant do the boring translation review.** The metadata YAML holds
`*_eng` back-translation fields. Ask the assistant to fill them, then read them
yourself. You find a wrong translation in a language that you do not speak.

**Keep the judgement.** An assistant is confident about search volume that
nobody outside Apple knows. Trust `aso discover` for what users type, and
trust `aso rank` for where you stand.

---

## 9. A team, and the record of the decisions

The workspace is in git, so the normal review process works for metadata.

- A metadata change is a pull request. The reviewer reads `aso diff`.
- A dismissal is a decision. The reason text goes into the database, and the
  strategy change goes into the commit message.
- `strategy.yaml` is the shared document. The `why` field of a seed keyword is
  where marketing and engineering agree.
- A `notes:` entry records a trade-off that the audit repeats in every run. Use
  it for the decisions that a new team member must not undo by accident.

The workspace `README.md` that `aso init` writes explains the layout to
somebody who never used the tool.

---

## 10. A quarterly health check

Apple changes the store. Run this every three months:

```bash
aso verify-groups --group US        # does the cross-localization table hold?
aso verify-groups --group DE
aso discover --deep                 # new query phrasings after an iOS season
aso assets                          # new device sizes in App Store Connect
aso history                         # is the open count going down?
```

Then read the evergreen checklist at the end of the report. It lists the levers
that no file audit can check: custom product pages, in-app events, screenshot
captions, rating recency, and retention.

If `aso verify-groups` disagrees with the built-in table,
[open an issue](https://github.com/AdmTal/aso-advisor/issues). The table
belongs to everybody who uses the tool.
