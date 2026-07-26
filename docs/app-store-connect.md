# App Store Connect: pull, push, and upload

Three commands talk to App Store Connect:

| Command | What it does |
| --- | --- |
| `aso pull` | Reads the metadata of your app into the workspace. |
| `aso push` | Sends the metadata of a version directory back. |
| `aso push-assets` | Uploads the localized screenshots and app preview videos. |

With them, the workspace holds the complete loop: read what is live, audit it,
change the YAML, review the change in a pull request, then publish it.

The other commands need none of this. The audit reads files, and the live
commands (`rank`, `discover`, `competitors`, `reviews`) read public endpoints.

- [Install the extra](#install-the-extra)
- [Make an API key](#make-an-api-key)
- [Tell the tool about the key](#tell-the-tool-about-the-key)
- [Keep the key safe](#keep-the-key-safe)
- [`aso pull`](#aso-pull)
- [`aso push`](#aso-push)
- [`aso push-assets`](#aso-push-assets)
- [The full loop](#the-full-loop)
- [In a build pipeline](#in-a-build-pipeline)
- [Errors that you will meet](#errors-that-you-will-meet)

---

## Install the extra

Apple wants a signed ES256 token, so these three commands need one more
package:

```bash
pipx install 'aso-advisor[sync]'
# or, if the tool is already installed with pipx:
pipx inject aso-advisor 'PyJWT[crypto]'
# or
pip install 'aso-advisor[sync]'
```

---

## Make an API key

You make the key one time, and every project of the same team can use it.

1. Sign in to [App Store Connect](https://appstoreconnect.apple.com/).
2. Go to **Users and Access → Integrations → App Store Connect API**.
3. Select **Team Keys**, then press the **plus** button.
4. Give the key a name, for example `aso-advisor`, and the role **App Manager**
   or higher. A lower role cannot change metadata.
5. Press **Generate**.
6. Press **Download**. Apple lets you download the `.p8` file **one time
   only**. Put it somewhere safe:

   ```bash
   mkdir -p ~/.appstoreconnect/keys
   mv ~/Downloads/AuthKey_ABCDE12345.p8 ~/.appstoreconnect/keys/
   chmod 600 ~/.appstoreconnect/keys/AuthKey_ABCDE12345.p8
   ```

7. Note two more values from the same page:
   - the **Key ID** in the table, for example `ABCDE12345`;
   - the **Issuer ID** at the top of the page, a long identifier with dashes.

If you lose the `.p8` file, you cannot download it again. Revoke the key and
make a new one.

---

## Tell the tool about the key

Three ways. The tool reads them in this order, and the first value wins.

### 1. Environment variables (the best way)

```bash
export APP_STORE_CONNECT_KEY_ID=ABCDE12345
export APP_STORE_CONNECT_ISSUER_ID=00000000-0000-0000-0000-000000000000
export APP_STORE_CONNECT_PRIVATE_KEY_PATH=~/.appstoreconnect/keys/AuthKey_ABCDE12345.p8
```

Put them in your shell profile, or in a password manager that exports them.

### 2. A `.env` file in the workspace

```bash
cat > aso/.env <<'EOF'
APP_STORE_CONNECT_KEY_ID=ABCDE12345
APP_STORE_CONNECT_ISSUER_ID=00000000-0000-0000-0000-000000000000
APP_STORE_CONNECT_PRIVATE_KEY_PATH=~/.appstoreconnect/keys/AuthKey_ABCDE12345.p8
EOF
```

`aso init` already writes `.env` into the `.gitignore` of the workspace.

### 3. The `asc:` block of `aso.yaml`

```yaml
asc:
  key_id: ABCDE12345
  issuer_id: 00000000-0000-0000-0000-000000000000
  private_key_path: ~/.appstoreconnect/keys/AuthKey_ABCDE12345.p8
  # app_id: 123456789   # the default is app.track_id
```

Use this only for the two identifiers. Never write the key itself into a file
that you commit.

### The app identifier

The commands also need the numeric identifier of the app. The tool takes
`app.track_id` from `aso.yaml`, which `aso init --app-id` already filled in.
The number is the same one that appears in your App Store page URL and in App
Store Connect under **App Information → Apple ID**.

### Test it

```bash
aso auth            # what the tool found
aso auth --check    # the same, and one call to Apple to confirm it
```

```
  key id      ABCDE12345
  issuer id   00000000-0000-0000-0000-000000000000
  key file    /Users/you/.appstoreconnect/keys/AuthKey_ABCDE12345.p8
  app id      123456789

✅ Apple accepted the key. The app is "Trailwise" (com.example.trailwise).
```

`aso auth` never prints the key itself.

---

## Keep the key safe

The `.p8` file is a long-lived credential with write access to your App Store
listing. Treat it like an SSH private key.

- Keep it outside the repository. `~/.appstoreconnect/keys/` is a good place.
- `aso init` puts `.env` and `*.p8` into the `.gitignore` of the workspace, and
  `aso auth` warns you when the key sits inside your project.
- In a build pipeline, use a secret. The variable
  `APP_STORE_CONNECT_PRIVATE_KEY` takes the content of the key, so the file
  never touches the disk of the runner.
- Revoke a key that you do not use. App Store Connect shows the last use of
  each key.

---

## `aso pull`

Read what is live into the workspace.

```bash
aso pull                          # the live version, into versions/<its name>/
aso pull --check                  # write nothing; report the differences
aso pull --editable               # the version that you prepare
aso pull --metadata-version 3.0   # write into a directory that you name
aso pull --locale de-DE           # one locale only
aso pull --force                  # overwrite work that nobody pushed
```

### `--check`: has anybody changed the metadata?

```
$ aso pull --check
live version: 2.1 (state READY_FOR_SALE)

⚠️  2 field(s) in 1 locale(s) differ from the store.

[en-US]
  subtitle:
    - store Offline Maps for Hiking
    + yours Offline Maps for Backpacking
  promotional_text: only in yours
    yours New in 2.2: park-wide downloads.

"yours" is the workspace, "store" is App Store Connect.
```

The command writes nothing and returns exit code 2 when the two do not match.
Run it every week in a job. It finds the change that a teammate made in the web
interface, and it tells you when the audit is reading YAML that is out of date.

### Your drafts are safe

A plain `aso pull` used to overwrite everything. Now the tool remembers the
values of the last pull and the last push, so it knows which side changed:

- the store changed and your files match the last sync → the pull writes;
- your files hold work that nobody pushed → the pull stops and shows it.

```
⛔ aso/versions/2.1 holds 2 field(s) in 1 locale(s) that the store does not have.
…
A pull would replace them. Choose one:
  aso pull --force                     take the store and lose the work above
  aso pull --metadata-version <name>   write the store into another directory
  aso push --dry-run                   send your work to the store instead
  aso pull --check                     only report, never write
```

The command writes one directory per version and keeps two things that only a
human can make:

- the `language:` note of each locale;
- every `*_eng` back-translation that you wrote for review.

Everything else comes from the store. The file names of a directory that
already exists stay the same, so a repository that came from another tool does
not change shape.

Run `aso pull` before an audit. The audit is only as correct as the YAML that
it reads.

---

## `aso push`

Send a version directory back to App Store Connect.

```bash
aso push --dry-run                # print the intended changes, send nothing
aso push                          # send them
aso push --locale de-DE           # one locale only
aso push --metadata-version 2.2   # a version that is not the newest
aso push --force                  # a version in WAITING_FOR_REVIEW
```

Four things happen before the first change:

1. **The length check**, on your machine. A field that is too long stops the
   push, and the message names the locale and the field.
2. **The audit.** A CRITICAL finding stops the push. Use `--skip-audit` when
   you disagree.
3. **The difference**, field by field, against the values that the store holds
   now:

   ```
   2 field(s) in 1 locale(s) would change:

   [en-US]
     keywords:
       - store gps,compass,elevation
       + new   gps,compass,elevation,waypoint
     promotional_text: only in new
       new   New in 2.2: park-wide downloads.
   ```

   A locale whose values already match is skipped, so a repeated push sends
   nothing and a push after a partial failure only finishes the rest.

4. **The backup.** The values of the store go into
   `state/backups/<timestamp>-before-push/` as YAML. To undo a push, copy those
   files into a version directory and push again. `--no-backup` switches it
   off.

Then the command works locale by locale:

```
[de-DE]
  version: updated abc123
  app info: updated def456
```

One bad locale does not stop the others, and the exit code is not zero when
any locale failed.

**What the command sends.** The version localization takes `description`,
`keywords`, `promotional_text`, `whats_new`, `marketing_url`, and
`support_url`. The app info localization takes `name`, `subtitle`, and
`privacy_policy_url`. A locale that App Store Connect does not have yet is
created.

**What the command never sends.** `language:` and every `*_eng` field. They
are notes for you.

---

## `aso push-assets`

Upload the localized screenshots and the app preview videos.

```bash
aso push-assets --dry-run         # the difference, with no upload
aso push-assets                   # upload what changed
aso push-assets --only videos
aso push-assets --locale de-DE --device iphone-6.9
aso push-assets --missing-only    # never replace what the store already holds
```

The command uploads **only what changed**. App Store Connect keeps an MD5
checksum per asset. When the checksums of a set are the same as your files, in
the same order, the tool skips the set:

```
[en-US/APP_IPHONE_67] up to date (3 screenshot(s))
[de-DE/APP_IPHONE_67] store=2 local=3 -> replacing
    uploaded 01-karte.png
    uploaded 02-hoehenprofil.png
    uploaded 03-wegpunkte.png
```

The default source is the assets tree of the version:

```
versions/2.1/assets/en-US/screenshots/iphone-6.9/01-hero.png
versions/2.1/assets/en-US/previews/iphone-6.9/01-demo.mp4
```

`--dir` and `--videos-dir` read a tree that lives somewhere else, for example
the export folder of a design tool. The directory names are read loosely:

```
English (en-US)/iOS Phones  6.9/01.png      locale first
en-US/phone/01.png                           locale first, short names
phone/01.png                                 flat, needs --locale or --all-locales
iPhone/en-US/app_preview.mp4                 device first, for videos
```

```bash
aso push-assets --dir "~/design/App Store Screenshots/Theme A" \
                --videos-dir "~/design/App Store Videos" --dry-run
```

Notes that save time:

- The file name order is the display order. Use `01-`, `02-`, `03-`.
- A set holds at most 10 screenshots and 3 app previews.
- App Store Connect has no 6.9-inch type. A 6.9-inch image uploads as the
  6.7-inch type, and the store shows it on the large devices.
- A locale needs its metadata localization first. Run `aso push` before
  `aso push-assets` for a new locale.
- Apple processes the uploads in the background. A screenshot appears after
  some minutes. A preview video takes longer.
- Run `aso assets` first. It finds a wrong pixel size or an alpha channel
  before the upload, not after it.

---

## The full loop

```bash
aso pull --check             # did anybody change the store since last time?
aso pull                     # take what is live today
aso audit                    # what to change
# edit aso/versions/2.2/*.yaml
aso audit --metadata-version 2.2
aso diff --old 2.1 --new 2.2 # read the change
aso push --dry-run           # what the push would do
aso push                     # publish the text
aso push-assets              # publish the images and the videos
aso pull --editable          # confirm what the store now holds
aso audit                    # the fixed items resolve by themselves
```

---

## In a build pipeline

Keep the key in a secret, and give the tool the content of the key:

```yaml
- name: Find the metadata that somebody changed by hand
  env:
    APP_STORE_CONNECT_KEY_ID: ${{ secrets.ASC_KEY_ID }}
    APP_STORE_CONNECT_ISSUER_ID: ${{ secrets.ASC_ISSUER_ID }}
    APP_STORE_CONNECT_PRIVATE_KEY: ${{ secrets.ASC_PRIVATE_KEY }}
  run: |
    pip install 'aso-advisor[sync]'
    aso pull --check          # exit code 2 when the store and the repository differ

- name: Push the metadata
  env:
    APP_STORE_CONNECT_KEY_ID: ${{ secrets.ASC_KEY_ID }}
    APP_STORE_CONNECT_ISSUER_ID: ${{ secrets.ASC_ISSUER_ID }}
    APP_STORE_CONNECT_PRIVATE_KEY: ${{ secrets.ASC_PRIVATE_KEY }}
  run: |
    pip install 'aso-advisor[sync]'
    aso push --dry-run
```

Start with `--dry-run` in the pipeline, and keep the real push manual until
you trust the diff.

---

## Errors that you will meet

**`No editable App Store version.`**
App Store Connect has no version in a state that accepts changes. Make the next
version in App Store Connect first, or use `--editable` with `aso pull` to read
what you prepare.

**`The newest editable version is in WAITING_FOR_REVIEW.`**
A change now can restart the review. Use `--force` when that is what you want.

**`HTTP 401`**
The token is wrong. Check that the Key ID belongs to the `.p8` file, and that
the Issuer ID is the one at the top of the Integrations page. `aso auth --check`
tells you in one call.

**`HTTP 403`**
The key has a role that cannot change metadata. Make a key with **App Manager**
or higher.

**`ENTITY_ERROR.ATTRIBUTE.INVALID` on `keywords`**
The keyword field is too long, or it holds a character that Apple refuses. Run
`aso audit`; the LIMIT rule finds it on your machine.

**`The localization does not exist` from `push-assets`**
The version has no localization for that locale yet. Run `aso push` first.

**`the store returned no upload operation`**
Apple refused the reservation, usually because the file is far too large or the
type is wrong. Check the file, then try again.
