# Keyword research: where the target phrases come from

`phrase_targets` drives the most valuable rule of the tool, the coverage
matrix, and `aso rank`. This page explains how to build that list, and how
`aso phrases` builds a first version of it for you.

- [The idea](#the-idea)
- [`aso phrases`](#aso-phrases)
- [How the score works](#how-the-score-works)
- [What the command filters out](#what-the-command-filters-out)
- [Write the result into the strategy](#write-the-result-into-the-strategy)
- [The other three sources](#the-other-three-sources)
- [A research sprint, end to end](#a-research-sprint-end-to-end)
- [How many phrases](#how-many-phrases)

---

## The idea

A target phrase is a query that you want to win. It must pass three tests:

1. **Somebody types it.** A phrase that you invented has no traffic, however
   well it describes the app.
2. **You can win it.** A query that a huge app owns is a bad first target.
3. **It brings the right user.** A user who searches "free video editor" and
   finds a paid hiking app leaves in ten seconds, and the store notices.

Nobody outside Apple knows the search volume. The App Store autocomplete is
the closest free signal: Apple sorts the completions by popularity, so the
position of a completion is a rank of demand. Every completion is also proof
of test 1, because it comes from real queries.

---

## `aso phrases`

```bash
aso phrases                       # propose phrases for the home storefront
aso phrases --country de          # for another storefront
aso phrases --roots "trail map,hiking gps"   # add your own roots
aso phrases --deep                # expand the best completion one more level
aso phrases --with-reviews        # also read the words of your users
aso phrases --limit 40
```

The command expands root terms through the autocomplete, adds the word groups
of your competitors' titles, then scores each candidate against the metadata
that you have today.

```
  score  phrase                                coverage                     why
     10  offline hiking maps                   needs offline (en-US)        autocomplete #1
      9  hiking gps tracker                    needs tracker (en-US)        autocomplete #2; 2 roots
      8  trail map offline                     covered by en-US             autocomplete #3; already covered by en-US
      7  backpacking route planner             needs planner (en-US)        autocomplete #5; in the title of Trail Buddy
      5  hiking app free                       needs hiking (en-US)         autocomplete #4; low value: app, free
```

Read the columns like this:

- **score** — how much the command believes in the phrase. It is a first
  opinion, not a fact.
- **coverage** — what your metadata does today. `covered by en-US` means one
  localization already holds every word, so the phrase can match. `needs …`
  names the missing words and the localization that is nearest.
- **why** — the reason for the score.

The roots come from your own strategy: `discovery_seeds`, the seed keywords
with a score of 6 or more, and the phrases that you already target. A better
strategy file therefore gives better proposals. `--roots` adds more for one
run.

---

## How the score works

The score starts from the position in the autocomplete: position 1 gives 10,
and position 12 gives 2. Then:

| Change | Reason |
| --- | --- |
| +1 | More than one root returned the phrase. Two paths to the same query mean a real cluster. |
| +1 | A tracked competitor holds the words in its title. A strong app does not choose a title by accident. |
| +0.5 | One of your localizations already covers it. The phrase costs nothing to keep. |
| −1 | Four words or more. The tail is long, and the volume is small. |
| −2 | A word of `low_value_terms`, such as `free` or `iphone`. The store ignores those words, so the phrase can never match in full. |
| −2 | A trademark of another company. The traffic is real, and so is App Review guideline 2.3.7. |

The result is between 1 and 10. It is deliberately simple: you can predict it,
and you can argue with it.

---

## What the command filters out

The autocomplete also returns the **names of apps**. A name is not a query, and
it makes a bad target. Two marks give a name away, and the command drops both:

- a separator that a brand uses: `Hiking Maps: Pro Edition`;
- a word that appears two times: `hiking hiking trail`.

The command also drops a phrase that you already target, and a phrase of more
than five words.

A one-word completion is not a phrase. If you do not index that word, the
command proposes it in a second list, **Single words worth a keyword slot**.

---

## Write the result into the strategy

```bash
aso phrases --write                 # add the phrases with a score of 6 or more
aso phrases --write --min-score 8   # only the strong ones
aso phrases --write-seeds           # add the one-word proposals as seeds
```

`--write` merges the proposals into `phrase_targets` in `strategy.yaml`. What
is there stays there, and a phrase is never added two times. The command
prints what it added.

Two points to know:

- The command rewrites the `phrase_targets:` block. The rest of the file,
  comments included, does not change, but a comment **inside** that block is
  lost.
- The scores are a first opinion. Open the file and correct them. You know
  which query brings a user who pays.

Then:

```bash
aso audit      # which phrases you cover, and what each gap needs
aso rank       # your real position for each of them
```

---

## The other three sources

`aso phrases` starts the list. These commands make it better.

**`aso discover`** shows the whole autocomplete result, with the `GAP` marker
for the words that your storefront group does not index. Use it when you want
the raw material and not an opinion.

```bash
aso discover --deep
aso discover --country de     # also uses local_discovery_seeds for de
```

A local-language root that returns nothing is a finding: that market does not
search your category in its own language.

**`aso reviews`** gives the words that your users write. Users search with the
words that they use. A word in three reviews or more, which you index nowhere,
is a strong seed.

**`aso competitors`** tells you when a strong app changes its title. That is
the best early signal that the keyword market moved. Take the new words and
put them into `aso phrases --roots`.

---

## A research sprint, end to end

Half a day, twice a year, or after a large feature.

```bash
# 1. What do people type?
aso phrases --deep --with-reviews --limit 40

# 2. Keep the good ones.
aso phrases --write --min-score 7
$EDITOR aso/strategy.yaml        # correct the scores, remove the wrong audience

# 3. What do the new targets need?
aso audit
```

The report now holds two things that you can act on: the coverage matrix per
storefront, and a proposed keyword field for each localization of your home
group.

```diff
- map,elevation,tracker,route,walk,trek,compass,summit,waypoint,park
+ map,elevation,tracker,route,walk,trek,compass,summit,waypoint,park,planner,offline
```

```bash
# 4. Publish, then measure.
aso push --dry-run && aso push
# wait two weeks
aso rank
```

Two weeks is the minimum. A keyword change needs time to enter the index, and
more time to collect the behaviour signals that decide the position.

---

## How many phrases

Between 10 and 25 for one app.

Fewer than 10, and the coverage matrix cannot show you a pattern. More than 25,
and every audit report holds a wall of MEDIUM findings that nobody reads.

Keep a mix:

- two or three **head** phrases, which you probably lose today, to measure the
  distance;
- ten or so **body** phrases in your category, which you can win this year;
- some **long-tail** phrases with clear intent, which convert best and which
  you can win now.

Delete a phrase when it stops describing the app. The list is a plan, not an
archive.
