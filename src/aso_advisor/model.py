"""Data structures and App Store field limits.

`LocaleMeta` holds the metadata of one localization. `Suggestion` is one audit
finding. Each suggestion gets a stable fingerprint (`fid`) from its rule, its
scope, and its subject. The fingerprint is what makes the advisor consistent:
the same problem keeps the same identifier in every run, so the tool can tell
you what is new, what is still open, and what you dismissed.
"""

import hashlib
import re
from dataclasses import dataclass, field

from .storefronts import NON_SPACED_LOCALES

# Maximum number of characters that App Store Connect accepts per field.
LIMITS = {
    'name': 30,
    'subtitle': 30,
    'keywords': 100,
    'promotional_text': 170,
    'description': 4000,
    'whats_new': 4000,
}

# Severity order, most important first.
SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']

# Bullet characters that localized descriptions use.
BULLET_CHARS = '•-·●'

# The App Store indexes these words for all apps. Do not spend characters
# on them.
IMPLICIT_TOKENS = {'app', 'apps'}

# The tokenizer splits on whitespace and punctuation. It does not match runs of
# `\w`, because `\w` excludes combining marks. A `\w` tokenizer breaks the
# scripts that write vowels as marks (Devanagari, Arabic) into single letters.
SEP_RE = re.compile(
    r"[\s​‌‍!-/:-@\[-`{-~¡¿·•‹›«»“”‘’„…—–،؛؟、。"
    r"！（），：；？]+"
)


def tokens(text):
    """Return the lowercase word tokens of `text`."""
    if not text:
        return []
    return [t for t in SEP_RE.split(text.lower()) if t]


def keyword_entries(raw):
    """Split a keyword field into its comma-separated entries."""
    if not raw:
        return []
    return [e.strip() for e in raw.replace('\n', ',').split(',') if e.strip()]


@dataclass
class LocaleMeta:
    """The metadata of one localization."""

    code: str
    language: str = ''
    name: str = ''
    subtitle: str = ''
    keywords: str = ''
    description: str = ''
    promotional_text: str = ''
    whats_new: str = ''

    @property
    def is_non_spaced(self):
        return self.code in NON_SPACED_LOCALES

    @property
    def kw_entries(self):
        return keyword_entries(self.keywords)

    @property
    def indexed_tokens(self):
        """Every word that the App Store can index for this localization.

        The set contains the words of the name, the subtitle, and the keyword
        field. Search phrases are made from this set, but only inside this one
        localization.
        """
        out = set(IMPLICIT_TOKENS)
        out.update(tokens(self.name))
        out.update(tokens(self.subtitle))
        for entry in self.kw_entries:
            out.update(tokens(entry))
        return out


@dataclass
class Suggestion:
    """One audit finding."""

    rule: str          # short rule identifier, for example 'DUP_XLOC'
    key: str           # the subject (keyword, phrase, or locale), for the fingerprint
    scope: str         # locale code, storefront group, or 'global'
    severity: str      # one of SEVERITIES
    title: str         # one-line summary
    detail: str = ''   # why the finding is important
    fix: str = ''      # the action to take
    # The persistence layer sets the fields below.
    fid: str = field(default='', compare=False)
    is_new: bool = field(default=False, compare=False)
    regressed: bool = field(default=False, compare=False)
    status: str = field(default='open', compare=False)

    def __post_init__(self):
        digest = hashlib.sha1(f'{self.rule}|{self.scope}|{self.key}'.encode()).hexdigest()
        self.fid = f'S-{digest[:8]}'

    @property
    def severity_rank(self):
        return SEVERITIES.index(self.severity)

    def to_dict(self):
        return {
            'id': self.fid,
            'rule': self.rule,
            'scope': self.scope,
            'severity': self.severity,
            'status': self.status,
            'title': self.title,
            'detail': self.detail,
            'fix': self.fix,
            'new': self.is_new,
            'regressed': self.regressed,
        }
