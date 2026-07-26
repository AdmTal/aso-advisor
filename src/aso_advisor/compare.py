"""Compare two sets of metadata, field by field.

Three commands need the same answer: `aso pull --check` (does the workspace
match the store?), `aso push --dry-run` (what would this push change?), and
`aso status` (is anything out of date?). They all call `diff_locales`.
"""

from dataclasses import dataclass

CHANGED = 'changed'
ONLY_LEFT = 'only_left'
ONLY_RIGHT = 'only_right'

FIELD_ORDER = ['name', 'subtitle', 'keywords', 'promotional_text', 'description',
               'whats_new', 'marketing_url', 'support_url', 'privacy_policy_url']


@dataclass
class Change:
    """One difference in one field of one locale."""

    locale: str
    field: str
    left: str = ''
    right: str = ''
    kind: str = CHANGED

    @property
    def sort_key(self):
        order = FIELD_ORDER.index(self.field) if self.field in FIELD_ORDER else 99
        return (self.locale, order, self.field)


def _text(value):
    return '' if value is None else str(value)


def diff_locales(left, right, fields=None, ignore_empty_right=True):
    """Differences between two `{locale: {field: value}}` dictionaries.

    `left` is what you have, `right` is what you compare against. With
    `ignore_empty_right`, a field that only `left` holds is reported as
    `ONLY_LEFT`, not as a change to an empty value.
    """
    out = []
    for locale in sorted(set(left) | set(right)):
        here = left.get(locale) or {}
        there = right.get(locale) or {}
        keys = set(here) | set(there)
        if fields is not None:
            keys &= set(fields)
        for field in sorted(keys):
            mine, theirs = _text(here.get(field)), _text(there.get(field))
            if mine == theirs:
                continue
            if not theirs and ignore_empty_right:
                out.append(Change(locale, field, mine, '', ONLY_LEFT))
            elif not mine:
                out.append(Change(locale, field, '', theirs, ONLY_RIGHT))
            else:
                out.append(Change(locale, field, mine, theirs, CHANGED))
    out.sort(key=lambda change: change.sort_key)
    return out


def shorten(text, width=64):
    """One line of at most `width` characters."""
    flat = ' '.join(_text(text).split())
    if len(flat) <= width:
        return flat
    return flat[:width - 1] + '…'


def format_changes(changes, left_label='local', right_label='store', width=64,
                   paint=None):
    """Readable lines for a list of changes, grouped by locale."""
    paint = paint or (lambda text, _color: text)
    lines = []
    current = None
    for change in changes:
        if change.locale != current:
            current = change.locale
            lines.append(f'[{current}]')
        if change.kind == ONLY_LEFT:
            lines.append(f'  {change.field}: only in {left_label}')
            lines.append('    ' + paint(f'{left_label:<5} {shorten(change.left, width)}',
                                        'green'))
        elif change.kind == ONLY_RIGHT:
            lines.append(f'  {change.field}: only in {right_label}')
            lines.append('    ' + paint(f'{right_label:<5} {shorten(change.right, width)}',
                                        'red'))
        else:
            lines.append(f'  {change.field}:')
            lines.append('    ' + paint(f'- {right_label:<5} {shorten(change.right, width)}',
                                        'red'))
            lines.append('    ' + paint(f'+ {left_label:<5} {shorten(change.left, width)}',
                                        'green'))
    return lines


def summarize(changes):
    """(number of locales, number of fields) that differ."""
    return len({change.locale for change in changes}), len(changes)
