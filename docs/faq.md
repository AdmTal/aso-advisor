# FAQ

## Does the tool change my app on the App Store?

No. The advisor reads YAML files that you control, and it reads the public
endpoints of Apple. It never writes to App Store Connect and it never needs
your credentials. To publish, use `fastlane deliver`, the App Store Connect
API, or the web interface.

## Do I need an API key or an account?

No. The live commands use three endpoints that anybody can call: the iTunes
Search and Lookup API, the MZSearchHints autocomplete, and the customer reviews
RSS feed. The only value that the tool needs is the numeric identifier of your
App Store page, which is in the page URL.

## Is it safe to run the live commands often?

Yes. The tool keeps each answer in the workspace database for 12 hours, and it
waits about three seconds between two uncached requests. That is under the
limit of about 20 requests per minute that Apple applies. A second run of the
same command answers from the cache and makes no request.

Use `--fresh` for one command when you need new data, and `aso cache --clear`
to empty the cache.

## Where does my data go?

Nowhere. Your metadata stays in your repository. The database stays in your
workspace. The only network requests are the live commands, and they only send
a search term and a country code to Apple.

## Does the tool know search volume?

No, and no free tool does. Apple gives popularity numbers to advertisers inside
Search Ads. Everything else is a model.

The tool uses the next best signal: the order of the App Store autocomplete.
Apple sorts those suggestions by popularity, so position 1 is the completion
with the most searches. `aso discover` shows that order.

## The suggestion is wrong for my app. What do I do?

Two answers.

For one finding: `aso dismiss S-1a2b3c4d "the reason"`. It never comes back,
and your reason stays in the database as the record of the decision.

For a whole rule: `audit.disable_rules: [RULE_ID]` in `aso.yaml`. `aso rules`
prints the identifiers.

If you think that the rule is wrong for everybody,
[open an issue](https://github.com/AdmTal/aso-advisor/issues). The rules encode
public research, not private truth.

## Why does the audit say a phrase is not covered when the words are all there?

Because they are in two localizations. The App Store makes a search phrase from
the words of ONE localization. Words from a second localization of the same
storefront make you findable for each word alone, never for the phrase. This is
the most valuable rule in the tool. Read
[concepts.md](concepts.md#a-phrase-comes-from-one-localization).

## Is the cross-localization table correct?

Apple does not publish it, and it has changed the membership before. The table
in this tool comes from public research. Test it against the live store:

```bash
aso verify-groups --group DE
```

If the result disagrees, correct it for your workspace with
`markets.storefront_groups_override`, and please open an issue so that
everybody gets the correction.

## Can I use it for Google Play?

Not yet. The rule engine has no Apple-specific code in its core, so the work is
possible: a Play workspace needs different field limits, no keyword field, and
a description that DOES feed the keyword index. Issues and pull requests are
welcome.

## Can I use it before my app is on the store?

Yes. Run `aso init` without `--app-id`. The audit works on your draft metadata
and finds the limit problems, the duplicates, and the phrase gaps before your
first submission. The live commands need a real identifier, so they stay quiet
until you have one.

## I have many apps. Does one installation work for all of them?

Yes. Install the tool one time, and put one workspace in each project. The tool
finds the workspace upwards from the current directory, and `--workspace` or
`ASO_WORKSPACE` names it directly. Each workspace keeps its own state.

## What happens if I delete the database?

The next audit reports every suggestion as new, and your dismissals are gone.
Nothing else breaks. The database holds no credentials and no unique data: the
suggestions come from your YAML files. Only the history and your decisions live
there.

## Why is the report file name a Unix timestamp?

Because two runs on one day must not overwrite each other, and because a
timestamp sorts correctly everywhere. `ls aso/reports/` gives you the runs in
order.

## Do the screenshots have to be in my repository?

No, but the tool audits them only when it can read them. Three options:

- Commit them. This is the simplest option, and it keeps the assets with the
  release that they belong to.
- Use [Git LFS](https://git-lfs.com/) for `aso/versions/**/assets/**`.
- Keep them in another place and make `assets` a symbolic link. The tool
  follows a symbolic link.

## The tool says my screenshot has the wrong size, but App Store Connect accepts it.

Apple changes the accepted sizes. The tool warns from a table that it carries;
App Store Connect is the authority. Add your size:

```yaml
assets:
  device_sizes:
    iphone-6.9: [[1320, 2868], [1290, 2796], [your, size]]
```

Or switch the check off with `assets.check_dimensions: false`, and please open
an issue with the size that Apple accepted.

## How often should I run the audit?

Run it when you change metadata, and one time each week with `aso rank` and
`aso competitors`. More often gives nothing: a keyword change needs about two
weeks before the position means anything.

## Why Python, and why only one dependency?

A metadata tool must still run in three years, in a repository that nobody
touched. One dependency (PyYAML) and the standard library make that likely.
`pipx install aso-advisor` also keeps it out of the environment of your
project.
