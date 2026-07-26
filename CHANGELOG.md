# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

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

[1.0.0]: https://github.com/AdmTal/aso-advisor/releases/tag/v1.0.0
