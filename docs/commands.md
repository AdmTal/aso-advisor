# Commands

Every command in one page. `aso --help` and `aso <command> --help` print the
same information in the terminal.

- [Global options](#global-options)
- [Exit codes](#exit-codes)
- [`aso init`](#aso-init)
- [`aso audit`](#aso-audit)
- [`aso list` · `show` · `dismiss` · `reopen` · `history`](#the-lifecycle-of-a-suggestion)
- [`aso versions` · `diff` · `assets` · `rules` · `where`](#the-workspace-commands)
- [`aso phrases`](#aso-phrases)
- [`aso rank`](#aso-rank)
- [`aso competitors`](#aso-competitors)
- [`aso discover`](#aso-discover)
- [`aso reviews`](#aso-reviews)
- [`aso verify-groups`](#aso-verify-groups)
- [`aso auth` · `pull` · `push` · `push-assets`](#app-store-connect)
- [`aso lookup` · `cache`](#the-helper-commands)

---

## Global options

| Option | What it does |
| --- | --- |
| `--workspace PATH` | Use this workspace. Without it, the tool searches upwards from the current directory. |
| `--version` | Print the version of the tool. |
| `-h`, `--help` | Print the help. |

The environment variable `ASO_WORKSPACE` does the same as `--workspace`. The
option wins over the variable.

`aso` without a command is the same as `aso audit`.

---

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | The command finished. |
| 1 | An error: no workspace, a broken YAML file, an unknown identifier. |
| 2 | `aso audit --fail-on` found a suggestion at that severity or above. |

---

## `aso init`

Make a new workspace.

```bash
aso init                                     # an empty workspace in ./aso
aso init --app-id 123456789                  # fill it from your live page
aso init --app-id https://apps.apple.com/us/app/x/id123456789
aso init --bundle-id com.example.app         # find the app by its bundle
aso init --path config/aso --locale de-DE --country de
```

| Option | Default | What it does |
| --- | --- | --- |
| `--app-id` | | The numeric identifier, or the App Store page URL. |
| `--bundle-id` | | Find the app by its bundle identifier. |
| `--path` | `./aso` | Where to write the workspace. |
| `--locale` | `en-US` | The primary locale. |
| `--country` | `us` | The home storefront. |
| `--metadata-version` | the live version | The name of the first version directory. |
| `--force` | | Overwrite the files that exist. |

With `--app-id` or `--bundle-id`, the command reads the public data of your app
and writes the name, the bundle identifier, and the first paragraph of the
description into the new files. The public data does not hold the subtitle or
the keyword field, so you add those by hand.

---

## `aso audit`

Audit a metadata version, write a report, and update the state. This is the
main command.

```bash
aso audit
aso audit --metadata-version 2.0             # audit what is live, not the draft
aso audit --json > audit.json                # for a script
aso audit --fail-on critical --no-state      # for a build pipeline
```

| Option | What it does |
| --- | --- |
| `--metadata-version NAME` | Audit this version. The default is the newest. |
| `--json` | Write the result as JSON to stdout, and print nothing else. |
| `--no-report` | Do not write a report file. |
| `--no-state` | Use a database in memory. The command writes nothing to disk. |
| `--no-assets` | Skip the screenshot and app preview rules. |
| `--fail-on LEVEL` | Return exit code 2 if a suggestion is at LEVEL or above. One of `critical`, `high`, `medium`, `low`, `info`, `none`. |

The report file is `aso/reports/aso-report-<unix timestamp>.md`. It holds the
action list, the phrase coverage matrix of every storefront, the proposed
keyword fields, the last live rank snapshot, the asset table, and the evergreen
checklist.

`--no-state` also means: no new run number, no resolved items, and no
dismissals. Use it in a pipeline, where a database has no value.

---

## The lifecycle of a suggestion

Each suggestion has a stable identifier, for example `S-1a2b3c4d`. The
identifier comes from the rule, the scope, and the subject. It stays the same
when the wording of the suggestion changes, so you can dismiss a suggestion one
time and never see it again.

```bash
aso list                              # the open suggestions
aso list --all                        # with the dismissed and resolved ones
aso list --severity critical,high     # only these severities
aso list --json                       # for a script

aso show S-1a2b3c4d                   # the full reason, the fix, the history

aso dismiss S-1a2b3c4d "we accept this trade-off"
aso reopen S-1a2b3c4d

aso history                           # the open count of each run, over time
```

A suggestion has four states:

| State | Meaning |
| --- | --- |
| `open` | It needs a decision. |
| `resolved` | The audit does not find it any more. The tool set the state. |
| `dismissed` | You decided against it. It stays quiet. |
| regressed | It was resolved, and it came back. The report marks it. |

---

## The workspace commands

```bash
aso versions      # the metadata versions, with their locale and asset counts
aso diff          # what changed between the two newest versions
aso diff --old 2.0 --new 2.1
aso assets        # the asset tree of the newest version, and its problems
aso assets --metadata-version 2.0
aso rules         # every rule identifier, for audit.disable_rules
aso where         # every path that the tool resolved
```

`aso where` is the first command to run when a result surprises you. It shows
which workspace the tool found.

---

## `aso phrases`

Propose the target search phrases. This is the command that builds
`phrase_targets`, which the coverage matrix and `aso rank` both use.

```bash
aso phrases
aso phrases --country de --deep
aso phrases --roots "trail map,hiking gps"
aso phrases --with-reviews --limit 40
aso phrases --write --min-score 7
```

| Option | Default | What it does |
| --- | --- | --- |
| `--country` | `app.default_country` | The storefront to read. |
| `--roots` | | Extra comma-separated root terms for this run. |
| `--deep` | | Expand the best completion one more level. |
| `--with-reviews` | | Also mine the words of your recent reviews. |
| `--limit` | 25 | How many rows to print. |
| `--write` | | Add the strong proposals to `phrase_targets`. |
| `--write-seeds` | | Add the one-word proposals to `seed_keywords`. |
| `--min-score` | 6 | The lowest score that `--write` accepts. |
| `--fresh` | | Do not use the cache. |

```
  score  phrase                          coverage                 why
     10  offline hiking maps             needs offline (en-US)    autocomplete #1
      9  hiking gps tracker              needs tracker (en-US)    autocomplete #2; 2 roots
      8  trail map offline               covered by en-US         autocomplete #3
```

The candidates come from the App Store autocomplete, from the titles of your
tracked competitors, and, with `--with-reviews`, from the words of your users.
The score comes from the position in the autocomplete, with a bonus for a
competitor title and a penalty for a low-value word or a trademark.

`docs/keyword-research.md` explains the whole method.


## `aso rank`

The real position of your app in the search results, for every brand phrase and
every target phrase of your strategy file.

```bash
aso rank
aso rank --countries us,gb,de --top 200
aso rank --fresh
```

| Option | Default | What it does |
| --- | --- | --- |
| `--countries` | `markets.rank_countries` | Comma-separated country codes. |
| `--top` | 100 | How many results to read per term. The maximum is 200. |
| `--fresh` | | Do not use the cache. |

```
== US ==
  term                                  rank  move           leader
  offline hiking maps                    #14  ▲ +9           Rival Maps
  hiking trail gps                       #38  ▼ -6           Rival Maps
  backpacking route planner                —  lost (was #91) Trail Buddy
  -> in the top 100 for 2/3 terms
```

The search endpoint returns the same ordered list that the store shows, so the
position is real, not a model. The tool stores each result, and the next run
prints the movement. The newest snapshot also appears in the audit report.

A term that shows `—` is not in the first `--top` results. Raise `--top` to 200
before you decide that the term is lost.

---

## `aso competitors`

A snapshot of the apps that you track, and the difference from the snapshot
before.

```bash
aso competitors
aso competitors --country de
aso competitors --suggest "hiking gps"     # find candidates to track
```

| Option | Default | What it does |
| --- | --- | --- |
| `--country` | `app.default_country` | The storefront to read. |
| `--suggest TERM` | | Print the top apps for TERM with their identifiers, and store nothing. |
| `--fresh` | | Do not use the cache. |

The command reports four signals:

- **A title change.** This is the strongest signal in the whole tool. A serious
  competitor changes the title only after keyword research. Check the words
  that they added.
- **A new version**, with the release date. It shows how fast they move.
- **A new description**, found by a hash. It usually means a conversion push or
  work on the discovery tags.
- **Rating velocity**, in ratings per day. It is the best free measure of
  install volume.

Run it every week. The value comes from the differences, and a difference needs
two snapshots.

---

## `aso discover`

Keyword ideas from the autocomplete of the App Store. Apple sorts the
suggestions by popularity, so position 1 is the completion with the most
searches. It is the closest free substitute for search volume.

```bash
aso discover
aso discover --country de        # also uses your local_discovery_seeds for de
aso discover --deep              # expand the best suggestion of each seed
```

| Option | Default | What it does |
| --- | --- | --- |
| `--country` | `app.default_country` | The storefront to read. |
| `--deep` | | Expand the first suggestion of each seed one more level. |
| `--fresh` | | Do not use the cache. |

```
  pos  suggestion                          status                  from
    2  offline hiking maps                 GAP: offline            hiking
    4  hiking gps tracker                  covered                 hiking
```

`GAP` names the words that no localization of that storefront group indexes. A
gap with a low position number is your best new keyword.

A local-language seed that returns nothing is also a finding: that market does
not search your category in its own language, so a translated keyword field
spends characters on queries that nobody types.

---

## `aso reviews`

The words of your users, and the recency of your rating.

```bash
aso reviews
aso reviews --countries us,gb,au --pages 3
```

| Option | Default | What it does |
| --- | --- | --- |
| `--countries` | `markets.review_countries` | Comma-separated country codes. |
| `--pages` | 3 | RSS pages per storefront. One page holds about 50 reviews. |
| `--fresh` | | Do not use the cache. |

The output has three parts:

- **The rating pulse.** The distribution of the stars, and the average of the
  last 30 days against the overall average. Rating recency is a ranking input,
  so a drop needs an answer.
- **The words that you do not index.** Users search with the words that they
  write. A word that appears in three reviews or more, and in no keyword field,
  is a candidate seed.
- **The recent reviews of three stars or less.** A fix list and a reply list.

---

## `aso verify-groups`

A live test of the cross-localization table.

```bash
aso verify-groups                # your home storefront
aso verify-groups --group DE
```

| Option | Default | What it does |
| --- | --- | --- |
| `--group` | `app.default_country` | The storefront group to test. |
| `--top` | 200 | How many results to read. |
| `--fresh` | | Do not use the cache. |

The command needs `probe.anchor` in your strategy file: the main category
phrase of your app.

For each localization of the group, the command finds a keyword that only that
localization holds. Then it searches `"<that keyword> <anchor>"` in the
storefront. If your app appears, that localization indexes there. The control
words, which no localization holds, must NOT return your app.

```
== verify-groups: Germany (de) — expected localizations ['de-DE', 'en-GB'] ==

  de-DE: "gipfel hiking maps" -> INDEXED (#3)
  en-GB: "ordnance hiking maps" -> INDEXED (#7)
  control: "dentist hiking maps" -> absent ✓
```

The test is only valid when the newest version in your workspace is the version
that is live on the store. Run it every quarter. Apple has changed the group
membership before.

---

## App Store Connect

These four commands need an API key that you make yourself, and the extra
dependency:

```bash
pipx install 'aso-advisor[sync]'
```

Read [app-store-connect.md](app-store-connect.md) for the key, the security
rules, and the errors that you will meet.

### `aso auth`

```bash
aso auth            # what credentials the tool found
aso auth --check    # the same, and one call to Apple to confirm them
```

With no credentials, the command prints the steps to make a key. It never
prints the key itself.

### `aso pull`

Read the metadata of the store into the workspace.

```bash
aso pull                          # the live version
aso pull --editable               # the version that you prepare
aso pull --metadata-version 3.0   # write into a directory that you name
aso pull --locale de-DE
```

The command keeps the `language:` notes and the `*_eng` back-translations of
the directory. Run it before an audit.

### `aso push`

Send a version directory to App Store Connect.

```bash
aso push --dry-run
aso push
aso push --locale de-DE
aso push --metadata-version 2.2 --force
aso push --skip-audit
```

| Option | What it does |
| --- | --- |
| `--metadata-version` | The version to push. The default is the newest. |
| `--dry-run` | Print the intended changes and send nothing. |
| `--locale` | One locale only. |
| `--force` | Allow a change to a version in WAITING_FOR_REVIEW. |
| `--skip-audit` | Push even when the audit finds a CRITICAL problem. |
| `--verbose` | Print the requests and the answers. |

The field lengths are checked on your machine, and the audit runs, before the
first request. One bad locale does not stop the others.

### `aso push-assets`

Upload the localized screenshots and the app preview videos. Only the sets
that changed go up; App Store Connect keeps a checksum per asset.

```bash
aso push-assets --dry-run
aso push-assets
aso push-assets --only videos --locale de-DE
aso push-assets --dir "~/design/Screenshots/Theme A" --videos-dir "~/design/Videos"
aso push-assets --missing-only
```

| Option | What it does |
| --- | --- |
| `--metadata-version` | The version whose assets to upload. |
| `--dir`, `--videos-dir` | Read a tree outside the workspace. |
| `--only screenshots\|videos` | One family only. |
| `--locale`, `--device` | One locale, or one device set. |
| `--all-locales` | A flat external tree applies to every localization. |
| `--missing-only` | Never replace what the store already holds. |
| `--dry-run`, `--force`, `--verbose` | As above. |


## The helper commands

```bash
aso lookup 123456789                       # the public data of an app
aso lookup https://apps.apple.com/us/app/x/id123456789
aso lookup --bundle-id com.example.app --country gb

aso cache                                  # how many answers are in the cache
aso cache --clear                          # empty it
```

`aso lookup` is the fastest way to find the numeric identifier that
`app.track_id` needs.

`aso cache --clear` is the answer when the store changed something and the
answers of the tool look old. Each live command also has `--fresh` for one run.
