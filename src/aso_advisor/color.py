"""Colour for the terminal, with the switches that users expect.

The tool writes colour only when it writes to a terminal. It stays plain when
you send the output to a file or to a pipe, when `NO_COLOR` is set (see
https://no-color.org/), or when the terminal says that it is `dumb`.
`FORCE_COLOR` turns it on again.
"""

import os
import sys

CODES = {
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'grey': '\033[90m',
    'bold': '\033[1m',
    'dim': '\033[2m',
}
RESET = '\033[0m'

# The colour of each severity in the reports.
SEVERITY_COLORS = {
    'CRITICAL': 'red',
    'HIGH': 'yellow',
    'MEDIUM': 'cyan',
    'LOW': 'grey',
    'INFO': 'grey',
}


def enabled(stream=None):
    """True when the output can take colour."""
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    if os.environ.get('TERM') == 'dumb':
        return False
    stream = stream or sys.stdout
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def paint(text, color, stream=None):
    """Wrap `text` in a colour, or return it unchanged."""
    code = CODES.get(color)
    if not code or not enabled(stream):
        return text
    return f'{code}{text}{RESET}'


def severity(name, text=None):
    """Colour a severity name, or any text, with the colour of that severity."""
    return paint(text if text is not None else name, SEVERITY_COLORS.get(name, ''))
