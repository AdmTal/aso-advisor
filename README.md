# ASO Advisor

ASO Advisor keeps track of your App Store metadata, tells you what to fix, and
automates the boring parts so it is easier to iterate.

[![CI](https://github.com/AdmTal/aso-advisor/actions/workflows/ci.yml/badge.svg)](https://github.com/AdmTal/aso-advisor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

```
$ aso audit

====================================================================
 ASO ADVISOR — metadata 2.1 · run #12
====================================================================
 open: 9   new: 2   regressed: 0   resolved: 4
 🟥 CRITICAL:0  🟧 HIGH:2  🟨 MEDIUM:5  ⬜ LOW:2  ℹ️ INFO:0
====================================================================

 ✅ RESOLVED since the run before:
    - es-MX: keywords that a cross-indexed title already gives: hike

 🟧 HIGH
   S-818e12f7 [NEW]  ja: keywords that the title already indexes: 地図, 山
              → Remove them from the keyword field and add new terms.
   S-44ba01c6        Branded search "trailwise" is not covered in: Germany
              → Put the words together in one localization per storefront.

 Report: aso/reports/aso-report-1753574400.md
```

Used for my apps:

- [Demo Scope](https://demoscope.app) —
  [App Store](https://apps.apple.com/us/app/hd-face-cam-screen-recorder/id6755395174?ct=aso-advisor&mt=8)
- [Lazy Blocks](https://apps.apple.com/us/app/lazy-blocks-endless-stack-zen/id6747955464?ct=aso-advisor&mt=8)

Good luck on your App Store optimization journey.

---

## Install

```bash
pipx install 'aso-advisor[sync]'
```

Python 3.9 or later. The audit needs PyYAML. The `sync` extra adds PyJWT for
the App Store Connect commands.

## Start

```bash
cd ~/projects/my-app
aso init --app-id 123456789     # the number in your App Store page URL
aso pull                        # or: aso import --fastlane fastlane/metadata
aso audit
```

To look first, audit the example app of this repository:

```bash
aso --workspace examples/trailwise audit --no-state --no-report
```

The walk-through is in [docs/getting-started.md](docs/getting-started.md).

## The workspace

One `aso/` directory per project. The tool finds it upwards from the current
directory, like git.

```
aso/
├── aso.yaml                    # app identity and markets
├── strategy.yaml               # brand, seed keywords, phrases, competitors
├── versions/2.1/
│   ├── titles_and_keywords.yaml
│   ├── descriptions.yaml
│   └── assets/en-US/screenshots/iphone-6.9/01-hero.png
├── reports/                    # generated
└── state/                      # generated
```

Commit `versions/` and the two YAML files. The rest is generated.
Specification: [docs/workspace.md](docs/workspace.md).

## Commands

| Command | What it does |
| --- | --- |
| `aso status` | Where the app stands, in one screen. |
| `aso audit` | Audit a version, write a report, remember every finding. |
| `aso list` · `show` · `dismiss` · `reopen` | Work the suggestions. |
| `aso phrases` | Propose the target search phrases. |
| `aso rank` | Your real position for each phrase, with the movement. |
| `aso discover` | Keyword ideas from the App Store autocomplete. |
| `aso competitors` | Title changes, version cadence, rating velocity. |
| `aso reviews` | The words of your users, and the rating pulse. |
| `aso pull` · `pull --check` | Read the store, or compare it with the workspace. |
| `aso push` · `push-assets` | Send the metadata, the screenshots, and the videos. |
| `aso import --fastlane` | Convert a `fastlane deliver` tree. |
| `aso assets` · `diff` · `versions` · `rules` | The small ones. |

Every option: [docs/commands.md](docs/commands.md).

## What the audit finds

Indexing:

- Fields that break the App Store Connect limits.
- Wasted characters: duplicates, spaces, unused budget, and words that your own
  title already indexes.
- Words that a **cross-indexed** localization gives you free.
- Target phrases whose words sit in two localizations, so they never combine.
- Singular and plural pairs, low-value words, and trademarks.
- Storefronts where your brand name does not find you.
- **In-app purchase names**: 30 indexed characters each, plus 45 for the
  description. Most apps leave them empty.
- **Screenshot captions**, from `assets/captions.yaml`. The store indexes them.

Conversion:

- Empty promotional text, thin release notes, and translations that dropped
  whole sections.
- Screenshots with the wrong size, an alpha channel, or a bad set count.
- App previews that are not 15 to 30 seconds long.

Every rule: [docs/rules.md](docs/rules.md).

## Live data, no account

`rank`, `discover`, `competitors`, and `reviews` read the public endpoints of
Apple. No key, no login. The answers are cached for 12 hours, and the requests
are throttled.

`pull`, `push`, and `push-assets` need an App Store Connect API key that you
make yourself. Run `aso auth`; with no key it prints the steps.

## In a build pipeline

```bash
aso audit --fail-on critical --no-state --no-report   # exit code 2 on a finding
aso pull --check                                      # exit code 2 on drift
```

A ready workflow file:
[examples/github-actions/aso-audit.yml](examples/github-actions/aso-audit.yml).

## Docs

| Document | Content |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, first workspace, first fix. |
| [The workspace](docs/workspace.md) | The folder and every setting. |
| [Commands](docs/commands.md) | Every command and option. |
| [Keyword research](docs/keyword-research.md) | Where the target phrases come from. |
| [App Store Connect](docs/app-store-connect.md) | The API key, then pull and push. |
| [Workflows](docs/workflows.md) | Weekly loop, release ritual, CI, many apps. |
| [Rules](docs/rules.md) | Every audit rule. |
| [Concepts](docs/concepts.md) | The store mechanics behind the rules, with sources. |
| [FAQ](docs/faq.md) | Short answers, and the limits. |

## Limits

- No search volume. Nobody outside Apple has it. The tool uses the popularity
  order of the autocomplete.
- No builds, no signing, no releases. Keep fastlane for those.
- No Google Play yet. Pull requests are welcome.
- Your data goes to Apple or nowhere. There is no server and no account.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
The documentation follows [ASD-STE100](https://www.asd-ste100.org/).

## License

MIT. See [LICENSE](LICENSE).
