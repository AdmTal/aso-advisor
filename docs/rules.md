# The rules

Every audit rule, with its severity, what it finds, and why it is important.
`aso rules` prints the same identifiers in the terminal.

Switch off a whole rule in `aso.yaml`:

```yaml
audit:
  disable_rules: [LOCALE, TITLE_REDUNDANT]
```

Hide one finding, and keep the rest of the rule, with
`aso dismiss S-1a2b3c4d "your reason"`.

The mechanics behind the rules are in [concepts.md](concepts.md).

| Severity | Meaning |
| --- | --- |
| 🟥 CRITICAL | App Store Connect refuses the upload. |
| 🟧 HIGH | You lose indexing, or you waste many characters. |
| 🟨 MEDIUM | A real opportunity. |
| ⬜ LOW | A small gain. |
| ℹ️ INFO | A record or a conscious bet. No action. |

---

## Hard limits

### `LIMIT` — 🟥 CRITICAL

A field is longer than App Store Connect accepts: name 30, subtitle 30,
keywords 100, promotional text 170, description 4000, release notes 4000.

**Why.** The upload fails. This is the one rule that is not an opinion.

**Fix.** Make the field shorter. In a build pipeline, use
`aso audit --fail-on critical` so that the pull request fails, and not the
upload.

---

## Wasted characters

### `FORMAT` — ⬜ LOW

The keyword field has a space next to a comma, an empty entry, or a comma at
the end.

**Why.** Each space uses one of the 100 characters and adds nothing. Three
spaces are a short keyword that you did not add.

**Fix.** `map,elevation,tracker`, never `map, elevation, tracker`.

### `EMPTY` — 🟧 HIGH

The subtitle or the keyword field of a locale is empty.

**Why.** The keyword field is 100 characters of indexing that no user sees. The
subtitle is the second strongest ranking field. An empty field is the largest
loss that the audit can find, and the easiest to fix.

**Fix.** Write them. The proposed keyword fields in the report are a start.

### `BUDGET` — 🟨 MEDIUM (keywords) / ⬜ LOW (name and subtitle)

A field does not use all of its characters.

**Why.** Unused characters are free ranking surface.

**Fix.** Add a term. For the name and the subtitle, add a word only when the
text still reads well for a human. A locale with a dense script correctly needs
fewer characters, so judge by meaning, not by the number.

### `DUP_FIELD` — 🟧 HIGH

The same entry is twice in one keyword field.

**Why.** The store indexes a word one time. The second copy is pure waste.

### `DUP_TITLE` — 🟧 HIGH

The keyword field holds a word that the name or the subtitle of the same locale
already holds.

**Why.** The store already indexes those words, with more weight. You pay
twice for one slot.

**Fix.** Remove the word from the keyword field and add a new term.

### `TITLE_SUB_DUP` — 🟧 HIGH

The same word is in the name and in the subtitle.

**Why.** These are your two strongest fields, and the repeat gives no extra
rank. It is the most expensive kind of duplicate.

**Fix.** Write the subtitle again with new search words.

### `MULTIWORD` — 🟨 MEDIUM

A keyword entry holds more than one word, for example `offline maps`.

**Why.** The store makes the phrases from the single words. The space buys
nothing.

**Fix.** Split the entry, then remove the words that are now duplicates.

### `PLURAL` — 🟨 MEDIUM

The singular form and the plural form are both in one keyword field.

**Why.** The store usually matches one form to the other. Both forms cost a
slot.

**Fix.** Keep the form that users type. `aso discover` and `aso reviews` show
which form that is.

### `LOWVALUE` — 🟨 MEDIUM

A keyword entry is in your `low_value_terms` list: `app`, `free`, `best`, and
also device names such as `iphone`.

**Why.** The store ignores some of these words or indexes them free. Device
names and platform names break the metadata rules of Apple.

**Fix.** Replace them with terms that users type.

---

## Cross-localization

These rules need the storefront group table. Read
[concepts.md](concepts.md#cross-localization) first.

### `DEAD_TITLE` — 🟧 HIGH

The keyword field of one localization pays for a word that the **title or
subtitle of a cross-indexed localization** already gives to that storefront.

**Why.** The store indexes titles and subtitles for the whole storefront. These
characters buy nothing.

**Two conditions keep the rule honest.** A word is waste only when it is
redundant in EVERY storefront where that localization appears. A word is never
waste when it holds up a target phrase inside its own localization, because a
phrase combines only within one localization.

### `DUP_XLOC` — 🟧 HIGH

Two localizations that index in the same storefront hold the same word in their
keyword fields.

**Why.** A word counts one time per storefront. Each repeat is a wasted slot.

**Fix.** The suggestion names the localization that must free the slot. The
tool keeps the word in the localization that needs it as the only carrier in
another storefront.

### `DUP_XLOC_STRUCT` — ℹ️ INFO

The same overlap, but every carrier is the only carrier of that word in some
other storefront group.

**Why it is only a note.** You cannot remove it without a loss somewhere else.
The rule exists so that you do not try.

### `TITLE_REDUNDANT` — ℹ️ INFO

A word in the name or the subtitle of one localization is also in the keyword
field of a cross-indexed localization.

**Why it is only a note.** The presence is redundant, but the weight is not. A
title outranks a keyword field. If you remove the word from the title, your app
stays indexed for it at lower weight. It is a question of whether those premium
characters have a better use, and only you can answer it.

---

## Brand, phrases, and seeds

### `BRAND` — 🟧 HIGH

A storefront cannot find you by the name that users say.

**Why.** A store title that starts with keywords often does not hold the brand
name. A user who heard your name then does not find you. Branded traffic
converts better than any other traffic, and this loss is invisible in a rank
report, because you never appear for the query at all.

**Fix.** Put every word of the brand phrase together in one localization per
storefront. The keyword field of your primary locale is usually the cheapest
place.

**Needs.** `brand_phrases` in your strategy file.

### `PHRASE` — 🟨 MEDIUM

No single localization of your home storefront holds every word of a target
phrase.

**Why.** The store makes a phrase from the words of ONE localization. A word in
another localization of the same group makes you findable for that word alone,
never for the phrase.

**Fix.** The suggestion names the nearest localization and the missing words.
Add the missing words there, in the name, the subtitle, or the keyword field.

The report shows the coverage of **every** storefront in a matrix. The rule
makes suggestions only for the home storefront, so the action list stays short.

**Needs.** `phrase_targets` in your strategy file.

### `SEED` — 🟨 MEDIUM

A seed keyword with a score of 5 or more is in no localization of your home
storefront.

**Why.** You said that the word is valuable, and you do not index it.

**Fix.** Add it where there are free characters, or exchange it for a weaker
term. The report proposes a complete new keyword field.

**Needs.** `seed_keywords` in your strategy file.

### `STRATEGY` — ℹ️ INFO

A note from your strategy file.

**Why.** A trade-off that you took on purpose must stay visible. A decision
that nobody repeats becomes an accident that nobody remembers.

### `TRADEMARK` — ℹ️ INFO

A keyword field holds a trademark of another company.

**Why it is only a note.** These terms often bring traffic that converts, and
they are a rejection risk under App Review guideline 2.3.7. The tool does not
make the decision for you. It keeps the bet visible. If a metadata rejection
names this guideline, these are the first terms to remove.

### `TRADEMARK_SOFT` — ℹ️ INFO

The same, for the names of platform features. The risk is lower.

---

## Descriptions and conversion

### `AI_TAGS` — ⬜ LOW

The first 500 characters of a description in your primary language do not hold
your core category words.

**Why.** Apple makes the discovery tags from your metadata, and assistants that
recommend apps read the description as plain text. Both need literal words, not
a slogan.

**Fix.** Put the missing words into the first two paragraphs in a natural way.

**Needs.** `ai_tag_terms` in your strategy file.

### `DESC_DEPTH` — 🟨 MEDIUM

A localized description has fewer paragraphs or fewer feature bullets than the
description of your primary locale.

**Why.** That market never reads the sections that the translation dropped, and
those sections are usually your benefit statements. The test uses the
structure, not the number of characters, because a character count punishes the
languages that are simply more compact.

**Fix.** Translate the missing sections and add them to the existing text. Do
not translate the whole description again, so that the terms already in use
stay the same.

### `PROMO` — 🟨 MEDIUM (empty) / ⬜ LOW (short)

The promotional text is empty, or it uses fewer than 80 of its 170 characters.

**Why.** It is the only field that you can change without a new release. It is
therefore your fastest conversion test.

### `WHATSNEW` — ⬜ LOW

The release notes are shorter than 40 characters.

**Why.** Returning visitors read them. They show that you maintain the app.
"Bug fixes and improvements" lowers conversion.

**Fix.** Name one concrete improvement for the user in each release.

---

## Coverage and history

### `LOCALE` — ⬜ LOW

A locale on your priority list has no metadata.

**Why.** Each localization adds 100 keyword characters and 60 title and
subtitle characters of indexing in its storefronts.

**Fix.** Copy the nearest localization that exists and translate it. Before you
translate, run `aso discover --country XX` with local-language seeds. If the
autocomplete of that storefront returns nothing for your category in the local
language, the market searches in English, and a translated keyword field spends
characters on queries that nobody types.

**Needs.** `locale_priority` in your strategy file.

### `DIFF` — ℹ️ INFO

What changed in the names, the subtitles, and the keyword fields since the
version before.

**Why.** Every metadata push gets a record. Months later, this is the entry
that explains a rank change.

---

## Assets

These rules read the file headers of the assets of the version. They use the
standard library only, and they never open the network. Switch all of them off
with `assets.check: false` or with `aso audit --no-assets`.

### `ASSET_COUNT` — 🟥 CRITICAL

A set holds more files than App Store Connect accepts: 10 screenshots or 3 app
previews per device set.

### `ASSET_SIZE` — 🟧 HIGH

A screenshot does not have a pixel size that its device set accepts.

**Note.** Apple changes the accepted sizes. The tool warns; it does not know
better than App Store Connect. Add a size with `assets.device_sizes`, or switch
the check off with `assets.check_dimensions: false`.

### `ASSET_ALPHA` — 🟧 HIGH

A screenshot has an alpha channel.

**Why.** App Store Connect refuses an image with transparency. This is a common
cause of a failed upload late on a release day.

**Fix.** Export the image again without an alpha channel, or put it on a solid
background.

### `ASSET_VIDEO_LENGTH` — 🟧 HIGH

An app preview is not between 15 and 30 seconds long.

### `ASSET_MISSING` — 🟨 MEDIUM

A locale in `assets.required_locales`, or your primary locale, has no
screenshots in this version.

**Why.** The store shows the screenshots of the primary language when a locale
has none. A localized screenshot with a translated caption converts better, and
the store indexes the caption text.

### `ASSET_DEVICE` — ⬜ LOW

The screenshots are not in a device directory, or the device name is not known.

### `ASSET_ORDER` — ⬜ LOW

A set has more than one file, and a file name does not start with a number.

**Why.** App Store Connect shows the assets in file name order. Names without a
number can change the order when you add a file.

**Fix.** `01-hero.png`, `02-features.png`, `03-pricing.png`.

### `ASSET_ORPHAN` — ⬜ LOW

An assets directory has a name that is not a locale of the metadata.

**Fix.** Rename the directory to an App Store locale code, or add the locale to
the metadata YAML.
