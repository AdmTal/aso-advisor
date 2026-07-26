# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [1.1.0] — 2026-07-26

The workspace is no longer read-only, and the tool now proposes the target
phrases instead of waiting for them.

### Added

- **`aso pull`, `aso push`, and `aso push-assets`.** The App Store Connect
  layer reads the live metadata into the workspace and sends the metadata, the
  localized screenshots, and the app preview videos back. `push-assets`
  uploads only the sets whose checksums changed, and it reads both the
  workspace tree and an external tree with loose directory names such as
  `English (en-US)/iOS Phones 6.9/`.
- **`aso auth`.** It finds the credentials in the environment, in a `.env`
  file, or in the `asc:` block of `aso.yaml`, prints what it found without the
  key itself, and with `--check` confirms that Apple accepts them. With no
  credentials it prints the steps to make an API key.
- **`aso phrases`.** It proposes the target search phrases from the App Store
  autocomplete, the titles of the competitors that you track, and the words of
  your reviews. It scores each candidate, marks what your metadata already
  covers, drops the app names that the autocomplete mixes in, and writes your
  choice into `strategy.yaml` with `--write`.
- Two guards before a metadata push: the field lengths, and the audit. A
  CRITICAL finding stops the push unless you pass `--skip-audit`.
- The `sync` extra, `pip install 'aso-advisor[sync]'`, which adds PyJWT. The
  audit still needs PyYAML alone.
- `asc:` settings in `aso.yaml`, and `.env` support in the workspace. `aso
  init` now writes `.env` and `*.p8` into the `.gitignore` of the workspace.
- Two documents: `docs/app-store-connect.md` (make a key, then pull, push, and
  upload) and `docs/keyword-research.md` (where the target phrases come from).

### Fixed

- **YAML 1.1 booleans.** A bare `no` in a YAML file is the boolean false, and
  `no` is the App Store locale code of Norway. `rank_countries: [us, no]` read
  as `['us', False]`, `locale_priority: {no: Norway}` lost its key, and a
  stopword list with `on` or `no` dropped those words. The loader now keeps
  them as text. `true` and `false` are still booleans.

## [1.0.0] — 2026-07-26

The first public release. The tool grew inside the metadata repository of
[Demo Scope](https://demoscope.app) and now works for any app.

### Added

- **The workspace.** One `aso/` directory in any project holds the
  configuration, the strategy, the versioned metadata YAML, and the localized
  screenshots and app previews. The tool searches for it upwards from the
  current directory, and `--workspace` or `ASO_WORKSPACE` names it directly.
- **`aso init`.** It writes a complete, commented workspace, and it fills the
  app identity from your live App Store page with `--app-id` or
  `--bundle-id`.
- **26 audit rules** for the metadata: hard limits, wasted characters,
  duplicates inside a locale and across cross-indexed locales, phrase
  coverage, brand coverage, seed keywords, low-value terms, trademarks,
  description depth, discovery-tag alignment, conversion fields, locale
  coverage, and a changelog between two versions.
- **8 asset rules** for the localized screenshots and app previews: pixel
  size, alpha channel, set size, preview duration, file order, and missing or
  orphan locales. The readers use the standard library only.
- **The state.** Each suggestion has a stable fingerprint, so a run reports
  what is new, what is still open, what your last push resolved, and what you
  dismissed. `aso list`, `show`, `dismiss`, `reopen`, and `history`.
- **The live layer**, on the public endpoints of Apple, with no account and no
  key: `aso rank`, `aso competitors` (with `--suggest` to find them),
  `aso discover`, `aso reviews`, and `aso verify-groups`. The answers are
  cached for 12 hours and the requests are throttled.
- **The workspace commands**: `aso versions`, `aso diff`, `aso assets`,
  `aso rules`, `aso where`, `aso lookup`, and `aso cache`.
- **A build-pipeline mode**: `--fail-on`, `--json`, `--no-state`, and
  `--no-report`, with an example GitHub Actions workflow.
- **The documentation**: a getting-started guide, the workspace specification,
  the command reference, the rule reference, the concepts behind the rules,
  ten workflows, and an FAQ.
- **An example workspace** for an app that does not exist, with real problems
  in it.

[1.1.0]: https://github.com/AdmTal/aso-advisor/releases/tag/v1.1.0
[1.0.0]: https://github.com/AdmTal/aso-advisor/releases/tag/v1.0.0
