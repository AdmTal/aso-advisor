# Contributing

Thank you for your interest. Issues, corrections, and pull requests are all
welcome.

## What helps the most

- **A correction to the cross-localization table.** Run
  `aso verify-groups --group XX`, and tell us what the live store answered.
  This table is the base of several rules, Apple does not publish it, and
  Apple changes it. A confirmed correction helps everybody who uses the tool.
- **A new screenshot size.** App Store Connect accepted a size that the tool
  does not know? Open an issue with the device set and the pixel size.
- **A rule that is wrong.** Explain the case where it gives bad advice. A rule
  that annoys people is a bug.
- **A new rule.** Bring the mechanic and a source, not only the idea.
- **Google Play support.** The rule engine has no Apple-specific code in its
  core. This is the largest open piece of work.

## Development setup

```bash
git clone https://github.com/AdmTal/aso-advisor.git
cd aso-advisor
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

```bash
make test        # pytest
make lint        # ruff
make check       # both, and an audit of the example workspace
```

No test opens the network. The tests of the live layer replace
`store_api._get`. Keep it that way: a test suite that needs the App Store is a
test suite that fails on a train.

## Before you open a pull request

1. `make check` passes.
2. New behaviour has a test.
3. A new rule has an entry in [`docs/rules.md`](docs/rules.md) and in
   `RULE_HELP` in `src/aso_advisor/rules.py`.
4. A new configuration field has an entry in
   [`docs/workspace.md`](docs/workspace.md).
5. The example workspace still audits without a CRITICAL finding.

## The shape of a rule

A rule is a function that takes a `RuleContext` and returns a list of
`Suggestion` objects. It reads; it never writes.

```python
def check_something(ctx):
    """One line that says what the rule finds."""
    out = []
    for meta in ctx.locales.values():
        if is_a_problem(meta):
            out.append(Suggestion(
                'RULE_ID',            # the identifier, also in ALL_RULES
                f'{meta.code}:subject',  # the subject, for the fingerprint
                meta.code,            # the scope: a locale, a group, or 'global'
                'MEDIUM',             # the severity
                'A short title that names the locale and the problem',
                detail='Why this is important. One or two sentences.',
                fix='The action to take. An imperative sentence.',
            ))
    return out
```

Then add the function to the list in `run_all()`, the identifier to
`ALL_RULES`, and one line to `RULE_HELP`.

Two rules for the fingerprint:

- The `key` must name the subject, not the wording. A suggestion keeps its
  identifier when you improve the title, and a user keeps their dismissal.
- The `key` must be stable between two runs with the same input.

## Style

**Code.** Follow the file that you edit. Ruff holds the line at 100 characters.
Single quotes. A docstring on each module and on each rule.

**Text.** The documentation and the messages of the tool follow
[ASD-STE100](https://www.asd-ste100.org/), Simplified Technical English. It is
a specification for technical writing that non-native readers can read quickly.
The rules that matter here:

- One idea per sentence. Twenty words or fewer for an instruction.
- Active voice. "The store indexes the word", not "the word is indexed".
- The imperative for an instruction. "Remove the duplicates."
- One word, one meaning. A "keyword field" is always a "keyword field", never
  a "keyword list" and never a "keyword string".
- The simple present tense. Avoid "will".
- No contractions, no slang, and no jokes that need a culture.
- Keep the articles. "The store indexes the word", not "store indexes word".

The style is not decoration. A large part of the audience of an ASO tool reads
English as a second language, and the subject is already difficult.

## Reporting a security problem

The tool reads local files and public HTTP endpoints, and it holds no
credentials. If you find something that behaves in another way, open an issue
with the details.

## License

Your contribution goes out under the MIT license of the project.
