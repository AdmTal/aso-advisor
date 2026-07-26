"""The ASO workspace: the folder that holds your metadata, your strategy, and
the state of the advisor.

A workspace is a directory with an `aso.yaml` file in it:

    aso/
    ├── aso.yaml          # app identity and market settings
    ├── strategy.yaml     # keywords, phrases, competitors — your ASO strategy
    ├── versions/         # one directory per metadata version
    ├── reports/          # generated reports (safe to delete)
    └── state/            # the SQLite database (safe to delete)

The tool finds the workspace in this order:

1. the `--workspace` option;
2. the `ASO_WORKSPACE` environment variable;
3. an `aso/` directory in the current directory or in a parent directory;
4. an `aso.yaml` file in the current directory or in a parent directory.

See `docs/workspace.md` for the full specification.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .storefronts import STOREFRONT_GROUPS

CONFIG_NAME = 'aso.yaml'
STRATEGY_NAME = 'strategy.yaml'
DEFAULT_DIRNAME = 'aso'

DEFAULT_PHRASE_STOPWORDS = {
    'with', 'and', 'on', 'for', 'the', 'a', 'an', 'of', 'to', 'in', 'my',
    'your', 'no', 'by',
}

DEFAULT_LOW_VALUE_TERMS = {
    'app', 'apps', 'free', 'best', 'top', 'new', 'ios', 'iphone', 'ipad',
    'download', 'apple',
}


class WorkspaceError(Exception):
    """The workspace is missing, or a file in it is not valid."""


# -- helpers ------------------------------------------------------------------

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _as_set(value, default=None):
    if value is None:
        return set(default or ())
    return {str(v).strip().lower() for v in _as_list(value) if str(v).strip()}


def _scored_items(value, key_name, default_score=5):
    """Read a scored list. Three shapes are valid:

        - term
        - [term, score]
        - {key_name: term, score: n, why: text}
    """
    out = []
    for item in _as_list(value):
        if isinstance(item, dict):
            term = item.get(key_name) or item.get('term') or item.get('value')
            if not term:
                continue
            out.append((str(term), int(item.get('score', default_score)),
                        str(item.get('why', '') or item.get('note', ''))))
        elif isinstance(item, (list, tuple)):
            term = str(item[0])
            score = int(item[1]) if len(item) > 1 else default_score
            why = str(item[2]) if len(item) > 2 else ''
            out.append((term, score, why))
        elif str(item).strip():
            out.append((str(item).strip(), default_score, ''))
    return out


# -- strategy -----------------------------------------------------------------

@dataclass
class Strategy:
    """The content of `strategy.yaml`. Every field is plain data."""

    brand_phrases: list = field(default_factory=list)
    seed_keywords: list = field(default_factory=list)      # [(term, score, why)]
    phrase_targets: list = field(default_factory=list)     # [(phrase, score, why)]
    phrase_stopwords: set = field(default_factory=lambda: set(DEFAULT_PHRASE_STOPWORDS))
    low_value_terms: set = field(default_factory=lambda: set(DEFAULT_LOW_VALUE_TERMS))
    trademark_terms: set = field(default_factory=set)
    soft_trademark_terms: set = field(default_factory=set)
    ai_tag_terms: list = field(default_factory=list)
    competitors: dict = field(default_factory=dict)        # {track_id: label}
    discovery_seeds: list = field(default_factory=list)
    local_discovery_seeds: dict = field(default_factory=dict)
    locale_priority: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)              # [(key, title, detail)]
    probe_anchor: str = ''
    probe_controls: list = field(default_factory=list)

    @property
    def phrase_words(self):
        """Every word that a target phrase needs, without the stopwords."""
        out = set()
        for phrase, _score, _why in self.phrase_targets:
            out.update(w for w in phrase.lower().split() if w not in self.phrase_stopwords)
        return out

    def seed_score(self, term):
        """The score of a seed keyword, or None."""
        low = term.lower()
        for seed, score, _why in self.seed_keywords:
            if seed.lower() == low:
                return score
        return None

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        competitors = {}
        raw_comp = data.get('competitors')
        if isinstance(raw_comp, dict):
            for track_id, label in raw_comp.items():
                competitors[int(track_id)] = str(label)
        else:
            for item in _as_list(raw_comp):
                if isinstance(item, dict):
                    track_id = item.get('track_id') or item.get('id')
                    if track_id is None:
                        continue
                    competitors[int(track_id)] = str(item.get('label')
                                                     or item.get('name') or track_id)
                else:
                    competitors[int(item)] = str(item)

        local_seeds = {}
        for country, terms in (data.get('local_discovery_seeds') or {}).items():
            local_seeds[str(country).lower()] = [str(t) for t in _as_list(terms)]

        notes = []
        for item in _as_list(data.get('notes') or data.get('strategy_notes')):
            if isinstance(item, dict):
                notes.append((str(item.get('key', item.get('title', 'note'))),
                              str(item.get('title', '')), str(item.get('detail', ''))))
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                notes.append((str(item[0]), str(item[1]), str(item[2])))

        probe = data.get('probe') or {}
        return cls(
            brand_phrases=[str(p).lower() for p in _as_list(data.get('brand_phrases'))],
            seed_keywords=_scored_items(data.get('seed_keywords'), 'term'),
            phrase_targets=_scored_items(data.get('phrase_targets'), 'phrase'),
            phrase_stopwords=_as_set(data.get('phrase_stopwords'), DEFAULT_PHRASE_STOPWORDS),
            low_value_terms=_as_set(data.get('low_value_terms'), DEFAULT_LOW_VALUE_TERMS),
            trademark_terms=_as_set(data.get('trademark_terms')),
            soft_trademark_terms=_as_set(data.get('soft_trademark_terms')),
            ai_tag_terms=[str(t).lower() for t in _as_list(data.get('ai_tag_terms'))],
            competitors=competitors,
            discovery_seeds=[str(t) for t in _as_list(data.get('discovery_seeds'))],
            local_discovery_seeds=local_seeds,
            locale_priority={str(k): str(v) for k, v in (data.get('locale_priority') or {}).items()},
            notes=notes,
            probe_anchor=str(probe.get('anchor', '') or ''),
            probe_controls=[str(t) for t in _as_list(probe.get('controls'))],
        )


# -- configuration ------------------------------------------------------------

@dataclass
class AppIdentity:
    name: str = ''
    bundle_id: str = ''
    track_id: int = 0
    primary_locale: str = 'en-US'
    default_country: str = 'us'


@dataclass
class AssetSettings:
    check: bool = True
    check_dimensions: bool = True
    check_video_duration: bool = True
    max_screenshots: int = 10
    max_previews: int = 3
    required_locales: list = field(default_factory=list)
    device_sizes: dict = field(default_factory=dict)   # device -> [[w, h], ...]


@dataclass
class Config:
    app: AppIdentity = field(default_factory=AppIdentity)
    rank_countries: list = field(default_factory=lambda: ['us'])
    review_countries: list = field(default_factory=lambda: ['us'])
    storefront_groups: dict = field(default_factory=lambda: dict(STOREFRONT_GROUPS))
    group_filter: list = field(default_factory=list)
    assets: AssetSettings = field(default_factory=AssetSettings)
    disabled_rules: set = field(default_factory=set)
    cache_hours: int = 12

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        app_data = data.get('app') or {}
        app = AppIdentity(
            name=str(app_data.get('name', '') or ''),
            bundle_id=str(app_data.get('bundle_id', '') or ''),
            track_id=int(app_data.get('track_id') or 0),
            primary_locale=str(app_data.get('primary_locale', 'en-US')),
            default_country=str(app_data.get('default_country', 'us')).lower(),
        )
        markets = data.get('markets') or {}
        groups = dict(STOREFRONT_GROUPS)
        for gid, value in (markets.get('storefront_groups_override') or {}).items():
            if isinstance(value, dict):
                groups[gid.upper()] = (str(value.get('name', gid)),
                                       [str(c) for c in _as_list(value.get('locales'))])
            else:
                groups[gid.upper()] = (gid.upper(), [str(c) for c in _as_list(value)])

        asset_data = data.get('assets') or {}
        device_sizes = {}
        for device, sizes in (asset_data.get('device_sizes') or {}).items():
            device_sizes[str(device).lower()] = [tuple(int(n) for n in size) for size in sizes]
        assets = AssetSettings(
            check=bool(asset_data.get('check', True)),
            check_dimensions=bool(asset_data.get('check_dimensions', True)),
            check_video_duration=bool(asset_data.get('check_video_duration', True)),
            max_screenshots=int(asset_data.get('max_screenshots', 10)),
            max_previews=int(asset_data.get('max_previews', 3)),
            required_locales=[str(c) for c in _as_list(asset_data.get('required_locales'))],
            device_sizes=device_sizes,
        )
        audit = data.get('audit') or {}
        return cls(
            app=app,
            rank_countries=[str(c).lower() for c in _as_list(markets.get('rank_countries'))
                            or [app.default_country]],
            review_countries=[str(c).lower() for c in _as_list(markets.get('review_countries'))
                              or [app.default_country]],
            storefront_groups=groups,
            group_filter=[str(g).upper() for g in _as_list(markets.get('storefront_groups'))],
            assets=assets,
            disabled_rules={str(r).upper() for r in _as_list(audit.get('disable_rules'))},
            cache_hours=int(data.get('cache_hours', 12)),
        )

    def groups(self):
        """The storefront groups to audit, after the filter of the configuration."""
        if not self.group_filter:
            return dict(self.storefront_groups)
        return {gid: self.storefront_groups[gid] for gid in self.group_filter
                if gid in self.storefront_groups}


# -- the workspace ------------------------------------------------------------

@dataclass
class Workspace:
    root: Path
    config: Config
    strategy: Strategy

    @property
    def versions_dir(self):
        return self.root / 'versions'

    @property
    def reports_dir(self):
        return self.root / 'reports'

    @property
    def state_dir(self):
        return self.root / 'state'

    @property
    def db_path(self):
        return self.state_dir / 'aso.sqlite3'

    @property
    def config_path(self):
        return self.root / CONFIG_NAME

    @property
    def strategy_path(self):
        return self.root / STRATEGY_NAME

    def require_track_id(self):
        if not self.config.app.track_id:
            raise WorkspaceError(
                'This command needs the numeric App Store identifier of your app.\n'
                f'Add it to {self.config_path}:\n\n'
                '  app:\n    track_id: 123456789\n\n'
                'To find the number, look at your App Store page URL. The number '
                'comes after "id". You can also run: aso lookup --bundle-id com.example.app')
        return self.config.app.track_id


def _read_yaml(path):
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as exc:
        raise WorkspaceError(f'{path} is not valid YAML:\n{exc}') from exc


def candidate_roots(start=None, explicit=None):
    """Every directory that can hold the workspace, most specific first."""
    if explicit:
        base = Path(explicit).expanduser()
        return [base, base / DEFAULT_DIRNAME]
    env = os.environ.get('ASO_WORKSPACE')
    if env:
        base = Path(env).expanduser()
        return [base, base / DEFAULT_DIRNAME]
    out = []
    here = Path(start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        out.append(directory / DEFAULT_DIRNAME)
        out.append(directory)
    return out


def find_workspace_root(start=None, explicit=None):
    """Return the directory of the workspace, or None."""
    for candidate in candidate_roots(start, explicit):
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    return None


def load(start=None, explicit=None):
    """Load the workspace. Raise `WorkspaceError` if there is none."""
    root = find_workspace_root(start, explicit)
    if root is None:
        looked = explicit or os.environ.get('ASO_WORKSPACE') or Path.cwd()
        raise WorkspaceError(
            f'No ASO workspace found from {looked}.\n'
            f'A workspace is a directory that contains {CONFIG_NAME}.\n'
            'To make one, run:  aso init')
    config = Config.from_dict(_read_yaml(root / CONFIG_NAME))
    strategy = Strategy.from_dict(_read_yaml(root / STRATEGY_NAME))
    return Workspace(root=root, config=config, strategy=strategy)
