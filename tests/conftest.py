"""Shared fixtures and small builders for the tests."""

import struct
import zlib
from pathlib import Path

import pytest

from aso_advisor import rules, workspace

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'trailwise'

MINIMAL_CONFIG = """\
version: 1
app:
  name: Test App
  bundle_id: com.example.test
  track_id: 111
  primary_locale: en-US
  default_country: us
markets:
  storefront_groups: [US, GB]
"""

MINIMAL_STRATEGY = """\
brand_phrases: [test app]
seed_keywords:
  - term: widget
    score: 9
    why: The category word.
phrase_targets:
  - phrase: widget maker
    score: 8
ai_tag_terms: [widget]
"""


def png_bytes(width, height, alpha=False):
    """A valid, tiny PNG of the given size."""
    color_type = 6 if alpha else 2
    channels = 4 if alpha else 3
    row = bytes([0]) + bytes([12, 34, 56, 255][:channels]) * width
    raw = row * height

    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))

    header = struct.pack('>IIBBBBB', width, height, 8, color_type, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def mp4_bytes(seconds, timescale=600):
    """A minimal MP4 header that reports `seconds` of duration."""
    mvhd_body = (struct.pack('>I', 0)                       # version and flags
                 + struct.pack('>I', 0) + struct.pack('>I', 0)   # creation, modification
                 + struct.pack('>I', timescale)
                 + struct.pack('>I', int(seconds * timescale))
                 + b'\x00' * 80)
    mvhd = struct.pack('>I', len(mvhd_body) + 8) + b'mvhd' + mvhd_body
    moov = struct.pack('>I', len(mvhd) + 8) + b'moov' + mvhd
    ftyp_body = b'isom' + struct.pack('>I', 512) + b'isomiso2'
    ftyp = struct.pack('>I', len(ftyp_body) + 8) + b'ftyp' + ftyp_body
    return ftyp + moov


def write_workspace(root, config=MINIMAL_CONFIG, strategy=MINIMAL_STRATEGY, versions=None):
    """Write a workspace on disk. `versions` is {name: {filename: text}}."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'aso.yaml').write_text(config, encoding='utf-8')
    (root / 'strategy.yaml').write_text(strategy, encoding='utf-8')
    for name, files in (versions or {}).items():
        directory = root / 'versions' / name
        directory.mkdir(parents=True, exist_ok=True)
        for filename, text in files.items():
            (directory / filename).write_text(text, encoding='utf-8')
    return root


def context(locales, strategy=None, groups=None, **kwargs):
    """A rule context around a dictionary of LocaleMeta objects."""
    from aso_advisor.storefronts import STOREFRONT_GROUPS
    return rules.RuleContext(
        locales=locales,
        strategy=strategy or workspace.Strategy(),
        groups=groups or {'US': STOREFRONT_GROUPS['US'], 'GB': STOREFRONT_GROUPS['GB']},
        **kwargs)


def rule_ids(found):
    return [s.rule for s in found]


@pytest.fixture
def example_workspace():
    return workspace.load(explicit=str(EXAMPLE))
