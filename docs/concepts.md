# Concepts: how App Store search works

Every rule of this tool comes from one of the mechanics below. Read this page
before you disagree with a suggestion. If a rule is wrong for your app,
disagree with confidence and dismiss it.

Apple does not publish the algorithm. The mechanics below come from public
research, from the documentation of App Store Connect, and from experiments
that anybody can repeat. The sources are at the end of the page.

- [The fields, and their weight](#the-fields-and-their-weight)
- [Each word is indexed one time](#each-word-is-indexed-one-time)
- [A phrase comes from ONE localization](#a-phrase-comes-from-one-localization)
- [Cross-localization](#cross-localization)
- [Singular and plural](#singular-and-plural)
- [The description does not feed keyword rank](#the-description-does-not-feed-keyword-rank)
- [The promotional text](#the-promotional-text)
- [Screenshots and captions](#screenshots-and-captions)
- [The signals that are not text](#the-signals-that-are-not-text)
- [What nobody outside Apple knows](#what-nobody-outside-apple-knows)
- [Sources](#sources)

---

## The fields, and their weight

| Field | Characters | Ranking weight | Visible to the user |
| --- | --- | --- | --- |
| Name | 30 | Strongest | Yes |
| Subtitle | 30 | Strong | Yes |
| Keyword field | 100 | Normal | No |
| Developer name | — | Some | Yes |
| In-app purchase names | 30 each | Some | Yes |
| Description | 4000 | None for keywords | Yes |
| Promotional text | 170 | None | Yes |

The name and the subtitle do two jobs at the same time: they rank, and they
sell. The keyword field only ranks, and no user reads it. Therefore the keyword
field is the correct place for the words that are useful but ugly.

**The consequence:** never spend a character of the name or the subtitle on a
word that the keyword field can hold, unless the word also helps a human to
choose your app.

---

## Each word is indexed one time

The store builds an index of the words of your metadata, per storefront. A word
enters the index one time. A second copy adds nothing.

The waste therefore has four shapes, and the tool has a rule for each one:

| Shape | Rule |
| --- | --- |
| The same entry twice in one keyword field | `DUP_FIELD` |
| A keyword that the own name or subtitle holds | `DUP_TITLE` |
| A word in both the name and the subtitle | `TITLE_SUB_DUP` |
| A word that a cross-indexed localization holds | `DEAD_TITLE`, `DUP_XLOC` |

Each recovered character is a character for a word that you do not have yet.
A keyword field of 100 characters holds about 12 words. Three duplicates are
25 percent of your keyword surface.

---

## A phrase comes from ONE localization

This mechanic is the most valuable thing in this tool, and the least known.

The store makes the search phrases from the words of your metadata. If your
keyword field holds `offline` and `maps`, you can match the query "offline
maps". You do not need the phrase as one entry — a space inside an entry only
costs a character.

**But the combination happens inside one localization.** A storefront can index
several localizations at the same time (see the next section), and a word from
each of them makes you findable for that single word. The words never combine
across the boundary of a localization.

An example:

```
en-US keyword field:   offline,maps
es-MX keyword field:   hiking
```

In the United States storefront, your app is findable for "offline", for
"maps", and for "hiking". It is findable for "offline maps". It is **not**
findable for "offline hiking maps", because no single localization holds all
three words.

The `PHRASE` rule and the coverage matrix of the report exist for this. The
matrix shows, per storefront, whether one localization holds every word of each
of your target phrases:

```
| Phrase                    | United States   | Germany                    |
| offline hiking maps (9)   | ❌ needs hiking | ❌ needs hiking+maps       |
| trail map offline (7)     | ✅ en-US        | ❌ needs trail+map         |
```

---

## Cross-localization

In many storefronts, the App Store indexes more than one localization. The
United States storefront, for example, indexes en-US and also the metadata of
several other localizations. Most non-English storefronts index the local
language and English (United Kingdom).

Two consequences follow, and they point in opposite directions:

**An opportunity.** Each extra localization of a group gives 100 more keyword
characters in that storefront. Some developers therefore write an English
keyword field in a localization that is not English, to get more keyword space
in their home storefront. That is a real technique with a real cost: the
storefront of that language then indexes no word of its own language. Make the
trade on purpose, and write it in `notes:` so that you see it in every run.

**A trap.** A word in two localizations of the same group is one wasted slot.
The tool separates two cases. When another group needs that locale as the only
carrier of the word, the overlap is structural and the tool says so
(`DUP_XLOC_STRUCT`). When it does not, the fix names the localization that must
free the slot (`DUP_XLOC`).

Apple does not publish the table of the groups, and it has changed the
membership before. The table of this tool is in
[`storefronts.py`](../src/aso_advisor/storefronts.py). You can test it against
the live store:

```bash
aso verify-groups --group DE
```

If reality does not match the table, correct the table for your workspace with
`markets.storefront_groups_override` and open an issue.

---

## Singular and plural

The store matches some plural forms to their singular form, and some other
forms not at all. The behaviour is not reliable, and it is not the same in
every language.

Two rules follow:

- Do not pay for both forms in the same keyword field (`PLURAL`). One slot is
  enough, and the second slot buys almost nothing.
- Index the form that users type. `aso discover` and `aso reviews` tell you
  which form that is. The word "hiking" is often more searched than "hike",
  and a keyword field with only "hike" cannot match "hiking maps" as a phrase.

---

## The description does not feed keyword rank

On the App Store, the description does not enter the keyword index. This is
the opposite of Google Play, and it is the most common mistake of a developer
who writes for both stores.

The description still does three important jobs:

1. **It sells.** It is the text that a hesitant user reads.
2. **It feeds the discovery tags of Apple.** The store generates tags from your
   metadata, and it uses them to place your app in categories and in the
   "you might also like" lists. Tags from a vague description are vague.
3. **Assistants read it.** Users now ask a language model for an app
   recommendation. A model reads your description and your reviews as plain
   text. A first paragraph that says literally what the app does is worth more
   than a slogan.

The `AI_TAGS` rule checks that the first 500 characters hold your core category
words. The `DESC_DEPTH` rule finds a translation that dropped whole sections,
because that market then never reads your benefit statements.

---

## The promotional text

The promotional text is 170 characters at the top of the product page. It has
no ranking weight, and it has one property that no other field has: **you can
change it without a new release.**

It is therefore the only place where you can test conversion copy quickly. Use
it for a limited-time message, for the answer to your most common review
complaint, or for the benefit that your current campaign promises.

An empty promotional text is a MEDIUM finding, and it is one of the cheapest
wins in the whole audit.

---

## Screenshots and captions

The store indexes the text in your screenshot captions. Real search phrases in
the captions therefore work twice: they help a user to understand the app in
one second, and they add text to the index.

Three points that the asset audit cannot check for you:

- The first two or three screenshots do most of the work. A user decides
  before the scroll.
- A localized screenshot with a translated caption converts better than an
  English screenshot in a market that does not read English.
- App Store Connect shows the assets in file name order. A numeric prefix
  removes every doubt.

The asset audit checks what a machine can check: the pixel size, the alpha
channel, the number of files per set, the duration of an app preview, and the
locales that have no assets. See [workspace.md](workspace.md).

---

## The signals that are not text

Your metadata is one half of the ranking. The other half is behaviour, and no
file in your repository can show it:

- **Downloads and download velocity**, per storefront.
- **Retention after the install.** A keyword win goes away if the users leave
  on day one. Pair each ASO push with an onboarding fix.
- **Rating value and rating recency.** Recent ratings have more weight than old
  ratings. Ask for a review after a success moment, and never reset the rating
  without a strong reason. `aso reviews` tracks the 30-day pulse.
- **Custom Product Pages.** You can link terms of your keyword field to a
  specific product page, and the store serves that page for those searches.
  Most apps do not use them.
- **In-app events**, which the store matches to search queries.

The evergreen checklist at the end of each report repeats this list, because it
is the part that a file audit can never find.

---

## What nobody outside Apple knows

Be careful with any tool, including this one, that claims more than this:

- **Search volume.** Apple gives a "popularity" number to advertisers in
  Search Ads, for some terms. Everything else is a model. The order of the
  autocomplete is the best free signal, and it is an order, not a volume.
- **The exact weight of each field.** The order is well tested. The numbers are
  not public.
- **The exact membership of the storefront groups.** Test it; do not trust it.
  That is why `aso verify-groups` exists.
- **Whether semantic matching now ranks you for a phrase that you do not fully
  index.** Sometimes it does. Full coverage in one localization is still the
  stronger position.

The tool prefers a rule that you can check to a number that looks precise.

---

## Sources

The rules encode public research. These sources are a good start:

- [AppTweak — App Store keyword research](https://www.apptweak.com/en/aso-blog/app-store-keyword-research-aso)
- [AppTweak — how to benefit from cross-localization](https://www.apptweak.com/en/aso-blog/how-to-benefit-from-cross-localization-on-the-app-store)
- [MobileAction — territory-level cross-localization](https://www.mobileaction.co/blog/app-store-cross-localization/)
- [aso.dev — cross-localization tables](https://aso.dev/metadata/cross-localization/)
- [SplitMetrics — App Store ranking factors](https://splitmetrics.com/blog/apple-app-store-ranking-factors/)
- [AppFollow — ASO news](https://appfollow.io/blog/aso-news)
- [Apple — App Store Connect help: app information](https://developer.apple.com/help/app-store-connect/reference/app-information)
- [Apple — Custom Product Pages](https://developer.apple.com/app-store/custom-product-pages/)

The live layer uses three public endpoints of Apple: the iTunes Search and
Lookup API, the MZSearchHints autocomplete, and the customer reviews RSS feed.
They are public, but they are not a documented, supported API. Apple can change
them.
