# FAQ

## Does the tool change my app on the App Store?

Only when you ask it to, and only with a key that you make yourself.

The audit and the live commands never write. They read your files and the
public endpoints of Apple.

Three commands do write: `aso pull` (which writes files on your machine),
`aso push` (which sends your metadata to App Store Connect), and
`aso push-assets` (which uploads your screenshots and videos). Each one has a
`--dry-run` option, and `aso push` refuses to start when the audit finds a
CRITICAL problem. Read [app-store-connect.md](app-store-connect.md).

## Do I need an API key or an account?

Not for the audit, and not for `rank`, `discover`, `competitors`, or
`reviews`. Those use three endpoints that anybody can call: the iTunes Search
and Lookup API, the MZSearchHints autocomplete, and the customer reviews RSS
feed. The only value that the tool needs is the numeric identifier of your App
Store page, which is in the page URL.

You need an App Store Connect API key only for `pull`, `push`, and
`push-assets`. Run `aso auth`; with no key, it prints the steps to make one.

## Where do I put the .p8 key file?

Outside your repository. `~/.appstoreconnect/keys/` is a good place. Then give
the tool the path with the environment variable
`APP_STORE_CONNECT_PRIVATE_KEY_PATH`, with a `.env` file in the workspace, or
with `asc.private_key_path` in `aso.yaml`.

Apple lets you download a `.p8` file one time only. If you lose it, revoke the
key in App Store Connect and make a new one. In a build pipeline, put the
content of the key in the secret `APP_STORE_CONNECT_PRIVATE_KEY`, so the file
never touches the disk of the runner.

## Can it replace fastlane deliver?

For metadata, screenshots, and app previews, yes. `aso pull`, `aso push`, and
`aso push-assets` cover that ground, and the workspace adds the audit, the
suggestion history, and the strategy file.

For everything else that fastlane does — certificates, builds, TestFlight,
release — keep fastlane. The two tools live together without trouble.

## How do I get target phrases if I have none?

Run `aso phrases`. It expands your seeds through the App Store autocomplete,
adds the word groups of your competitors' titles, and scores each candidate
against the metadata that you have. `aso phrases --write` puts the strong ones
into `strategy.yaml`. See [keyword-research.md](keyword-research.md).

## Is it safe to run the live commands often?

Yes. The tool keeps each answer in the workspace database for 12 hours, and it
waits about three seconds between two uncached requests. That is under the
limit of about 20 requests per minute that Apple applies. A second run of the
same command answers from the cache and makes no request.

Use `--fresh` for one command when you need new data, and `aso cache --clear`
to empty the cache.

## Where does my data go?

To Apple, or nowhere.

Your metadata stays in your repository, and the database stays in your
workspace. The live commands send a search term and a country code to the
public endpoints of Apple. The push commands send your own metadata and your
own assets to App Store Connect, which is where they belong. Nothing goes
anywhere else, and the tool has no server.

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

## Why Python, and why almost no dependencies?

A metadata tool must still run in three years, in a repository that nobody
touched. The tool needs PyYAML and nothing else. The HTTP, the image and video
readers, and the database all come from the standard library.

The App Store Connect commands add one package, PyJWT, because Apple wants a
signed ES256 token. It is an extra, so a user who only wants the audit never
installs it: `pip install 'aso-advisor[sync]'`.

`pipx install aso-advisor` also keeps the tool out of the environment of your
project.
