"""YAML reading for the tool.

The loader here is `yaml.SafeLoader` with one change: it does not turn `no`,
`yes`, `on`, and `off` into booleans.

The change is necessary, not a taste. YAML 1.1 reads a bare `no` as false, and
`no` is the App Store locale code of Norway. The same rule breaks a keyword
such as `on` and a stopword list that holds `no`. With the standard loader,

    rank_countries: [us, no]
    locale_priority:
      no: Norway

reads as `[('us', False)]` and `{False: 'Norway'}`. The loader below reads both
as the text that you wrote. `true` and `false` stay booleans.
"""

import re

import yaml


class SafeLoader(yaml.SafeLoader):
    """A safe loader that keeps `no`, `yes`, `on`, and `off` as text."""


SafeLoader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers
            if tag != 'tag:yaml.org,2002:bool']
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

SafeLoader.add_implicit_resolver(
    'tag:yaml.org,2002:bool',
    re.compile(r'^(?:true|True|TRUE|false|False|FALSE)$'),
    list('tTfF'))


def load(text):
    """Read a YAML document. Returns None for an empty document."""
    return yaml.load(text, Loader=SafeLoader)      # noqa: S506 - SafeLoader subclass


def load_path(path):
    """Read a YAML file. Returns {} when the file is missing or empty."""
    from pathlib import Path

    path = Path(path)
    if not path.is_file():
        return {}
    return load(path.read_text(encoding='utf-8')) or {}
