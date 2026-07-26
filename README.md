# ASO Advisor

**A command-line App Store Optimization advisor for your app metadata.**
It reads the metadata that you keep in your own repository, finds the waste and
the gaps, and remembers every suggestion between runs. It reads the public
endpoints of Apple for real search positions, competitor moves, autocomplete
data, and your reviews. It proposes the target phrases to chase. And it can
pull your live metadata from App Store Connect, then push the text, the
screenshots, and the app previews back.

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
    - en-US: the keyword field has spaces next to commas
    - es-MX: keywords that a cross-indexed title already gives: hike

 🟧 HIGH
   S-aeec2a35 [NEW]  de-DE/iphone-6.9: 1 screenshot(s) have an unexpected size
              → Export the images again at the correct size.
   S-818e12f7        ja: keywords that the title or the subtitle already indexes: 地図, 山
              → Remove them from the keyword field and add new terms.

 Report: aso/reports/aso-report-1753574400.md
```

---

## Why this tool exists

A keyword tracker tells you where you rank. It does not tell you that your
Japanese keyword field pays for three words that your Japanese title already
indexes, or that the words of your best target phrase sit in two different
localizations and therefore never combine.

The ASO Advisor answers a different question: **given the metadata that you
have, what should you change next?** It gives the same answer every time, it
keeps its memory between runs, and it stays quiet about the suggestions that
you dismissed.

| A keyword tracker | The ASO Advisor |
| --- | --- |
| Where do I rank today? | What should I change next? |
| A dashboard on a website | A CLI in your repository, next to your code |
| A monthly bill | MIT, free, one dependency |
| Your data on their server | Your data in your git history |

## Install

```bash
pipx install aso-advisor              # recommended: an isolated tool install
pipx install 'aso-advisor[sync]'      # with the App Store Connect commands
# or
pip install 'aso-advisor[sync]'
# or, from the source
git clone https://github.com/AdmTal/aso-advisor.git && pip install -e aso-advisor
```

Python 3.9 or later. The audit needs PyYAML and nothing else. The `sync` extra
adds PyJWT, which `aso pull`, `aso push`, and `aso push-assets` use to sign the
token that Apple asks for.

## Sixty-second start

```bash
cd ~/projects/my-app
aso init --app-id 123456789    # the number in your App Store page URL
```

The command writes a workspace: a directory named `aso/` with a configuration
file, a strategy file, and a first version directory. Put your live metadata
into the version YAML, then:

```bash
aso pull         # or fill the version YAML by hand
aso audit        # audit the newest version, write a report
aso list         # the open suggestions
aso show S-1a2b3c4d
aso dismiss S-1a2b3c4d "a deliberate bet"
aso phrases      # propose the target search phrases
aso push         # send the metadata back to App Store Connect
aso push-assets  # upload the localized screenshots and videos
```

Read the [getting-started guide](docs/getting-started.md) for the full
walk-through. To see the tool work before you write anything, audit the example
workspace of this repository:

```bash
aso --workspace examples/trailwise audit --no-state --no-report
```

## The workspace: one folder in any project

The advisor is a utility, not a framework. Each project keeps its own
workspace. The tool searches for it upwards from the current directory, in the
same way as git.

```
my-app/
├── src/…
└── aso/
    ├── aso.yaml                  # app identity, markets, asset settings
    ├── strategy.yaml             # brand, seed keywords, phrases, competitors
    ├── versions/
    │   ├── 2.0/…                 # the metadata that you published before
    │   └── 2.1/
    │       ├── titles_and_keywords.yaml
    │       ├── descriptions.yaml
    │       └── assets/
    │           ├── en-US/screenshots/iphone-6.9/01-hero.png
    │           ├── en-US/previews/iphone-6.9/01-demo.mp4
    │           └── de-DE/screenshots/iphone-6.9/01-start.png
    ├── reports/                  # generated, not in version control
    └── state/                    # SQLite state, not in version control
```

Your metadata, your screenshots, and your strategy stay in your repository,
under version control, next to the code of the release that they belong to.
The tool never writes to App Store Connect. The full specification is in
[docs/workspace.md](docs/workspace.md).

## What the audit finds

**Indexing and organic reach**

- Fields that break the character limits of App Store Connect.
- Characters that you waste: spaces in the keyword field, unused budget,
  duplicate entries, and words that your own title already indexes.
- Words that a **cross-indexed** localization already gives you free. In many
  storefronts the App Store indexes more than one localization, so the same
  word in a second keyword field is a dead slot.
- Target phrases whose words sit in two localizations and therefore never
  combine into a phrase.
- Singular and plural pairs that pay twice.
- Low-value words, and trademarks of other companies. A trademark is a review
  risk, so the tool keeps it visible as a conscious bet.
- Brand coverage: the storefronts where a user who knows your name cannot find
  you.
- Locales with no metadata, in the order of your own priority list.

**Conversion**

- An empty or short promotional text — 170 characters that you can change
  without a release.
- Descriptions that a translation made shorter, so that market never reads
  your best benefit statements.
- The words that Apple needs in your description to make correct discovery
  tags.
- Thin release notes.

**Localized assets**

- Screenshots with the wrong pixel size, or with an alpha channel that App
  Store Connect refuses.
- Sets that are too large, app previews that are not 15 to 30 seconds long,
  and file names that do not show the display order.
- Locales that have metadata but no screenshots.

Every rule, with its severity and its reason, is in
[docs/rules.md](docs/rules.md).

## The target phrases, proposed for you

`phrase_targets` drives the most valuable rule of the tool. You do not have to
invent the list. Ask the store:

```bash
aso phrases --write
```

```
  score  phrase                          coverage                 why
     10  offline hiking maps             needs offline (en-US)    autocomplete #1
      9  hiking gps tracker              needs tracker (en-US)    autocomplete #2; 2 roots
      8  trail map offline               covered by en-US         autocomplete #3
      7  backpacking route planner       needs planner (en-US)    in the title of Trail Buddy
```

The candidates come from the App Store autocomplete (Apple sorts it by
popularity), from the titles of the competitors that you track, and from the
words of your own reviews. The command drops the app names that the
autocomplete mixes in, lowers the score of a phrase that holds a word the store
ignores, and marks the phrases that a trademark makes risky. `--write` puts the
strong ones into your strategy file.

[docs/keyword-research.md](docs/keyword-research.md) explains the method.

## Live data from the public endpoints of Apple

Five commands read the store itself. They need no account and no key. The tool
caches each answer for 12 hours and waits between requests, so you can run them
as often as you want.

```bash
aso rank            # the real position of your app for each target phrase
aso competitors     # title changes, version cadence, rating velocity
aso discover        # the autocomplete of the App Store, in popularity order
aso reviews         # the words of your users, and the 30-day rating pulse
aso verify-groups   # a live test of the cross-localization table
```

`aso rank` keeps a history, so the next run shows the movement:

```
== US ==
  term                                  rank  move           leader
  offline hiking maps                    #14  ▲ +9           Rival Maps
  hiking trail gps                       #38  ▼ -6           Rival Maps
  backpacking route planner                —  lost (was #91) Trail Buddy
```

## Pull and push, with your own App Store Connect key

The workspace is not read-only. With an API key that you make yourself, the
whole loop lives in your repository:

```bash
aso auth            # the steps to make a key, then a check that Apple accepts it
aso pull            # the live metadata of every locale, into the workspace
aso push --dry-run  # exactly what a push would change
aso push            # send the text back
aso push-assets     # upload the localized screenshots and app previews
```

`aso push-assets` uploads only the sets that changed: App Store Connect keeps
a checksum per asset, and the tool compares it with your files. It reads the
assets tree of the workspace, or any tree that you point it at with `--dir`,
including the folder names that design tools produce
(`English (en-US)/iOS Phones 6.9/01.png`).

Two guards run before a push: the field lengths, and the audit. A CRITICAL
finding stops the push, so a field that is too long fails on your machine and
not one hour later in App Store Connect.

[docs/app-store-connect.md](docs/app-store-connect.md) has the key steps, the
security rules, and the errors that you will meet.

## In a build pipeline

`aso audit --fail-on critical` returns exit code 2 when a suggestion is at that
severity or above. A metadata field that is too long then fails the pull
request, not the upload.

```yaml
- run: pipx install aso-advisor
- run: aso audit --fail-on critical --no-state --no-report
```

A complete workflow file is in
[examples/github-actions/aso-audit.yml](examples/github-actions/aso-audit.yml).

## Documentation

| Document | Content |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, first workspace, first fix. Start here. |
| [The workspace](docs/workspace.md) | The folder specification and every configuration field. |
| [Commands](docs/commands.md) | Every command and every option. |
| [Keyword research](docs/keyword-research.md) | Where the target phrases come from, and how `aso phrases` builds them. |
| [App Store Connect](docs/app-store-connect.md) | Make an API key, then pull, push, and upload the assets. |
| [Workflows](docs/workflows.md) | How people use the tool: the weekly loop, the release ritual, a keyword sprint, CI, many apps, AI assistants. |
| [Rules](docs/rules.md) | Every audit rule: what it finds, why, and how to fix it. |
| [Concepts](docs/concepts.md) | The App Store search mechanics that the rules encode, with sources. |
| [FAQ](docs/faq.md) | Short answers, and the limits of the tool. |

## What the tool does not do

- It does not know your search volume. Nobody outside Apple does. The tool uses
  the popularity order of the autocomplete, which is the best free substitute.
- It does not build, sign, or release your app. Keep fastlane for that. This
  tool covers the metadata, the screenshots, and the app previews.
- It does not support Google Play yet. The rule engine is store-agnostic, so
  the work is possible. Issues and pull requests are welcome.
- It does not send your data anywhere except to Apple: to the public endpoints
  when you run a live command, and to App Store Connect when you push. There is
  no server, and there is no account.

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md)
for the development setup, the test commands, and the writing style of the
project.

## Who made this

The tool grew inside [Demo Scope](https://demoscope.app), an iOS app that
records your screen and your face at the same time, with live touch
indicators, a teleprompter, and RTMP streaming. The advisor manages the
metadata of Demo Scope in more than 30 locales. Now it is free for everybody.

If the tool helps your app, look at
[Demo Scope on the App Store](https://apps.apple.com/us/app/hd-face-cam-screen-recorder/id6755395174?ct=aso-advisor&mt=8).

## License

MIT. See [LICENSE](LICENSE).
