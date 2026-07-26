import pytest

from aso_advisor import workspace
from aso_advisor.workspace import WorkspaceError
from conftest import write_workspace


def test_load_reads_config_and_strategy(tmp_path):
    root = write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(root))
    assert ws.config.app.name == 'Test App'
    assert ws.config.app.track_id == 111
    assert ws.strategy.brand_phrases == ['test app']
    assert ws.strategy.seed_keywords == [('widget', 9, 'The category word.')]
    assert ws.strategy.phrase_targets == [('widget maker', 8, '')]


def test_workspace_paths(tmp_path):
    root = write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(root))
    assert ws.versions_dir == root / 'versions'
    assert ws.db_path == root / 'state' / 'aso.sqlite3'
    assert ws.reports_dir == root / 'reports'


def test_explicit_path_may_be_the_parent(tmp_path):
    write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(tmp_path))
    assert ws.root == tmp_path / 'aso'


def test_search_walks_up_the_tree(tmp_path):
    write_workspace(tmp_path / 'aso')
    deep = tmp_path / 'src' / 'app' / 'ui'
    deep.mkdir(parents=True)
    assert workspace.find_workspace_root(start=deep) == tmp_path / 'aso'


def test_missing_workspace_explains_the_fix(tmp_path):
    with pytest.raises(WorkspaceError, match='aso init'):
        workspace.load(explicit=str(tmp_path / 'nothing'))


def test_broken_yaml_names_the_file(tmp_path):
    root = tmp_path / 'aso'
    root.mkdir()
    (root / 'aso.yaml').write_text('app:\n  - [broken\n')
    with pytest.raises(WorkspaceError, match='not valid YAML'):
        workspace.load(explicit=str(root))


def test_defaults_when_files_are_almost_empty(tmp_path):
    root = tmp_path / 'aso'
    root.mkdir()
    (root / 'aso.yaml').write_text('version: 1\n')
    ws = workspace.load(explicit=str(root))
    assert ws.config.app.primary_locale == 'en-US'
    assert ws.config.rank_countries == ['us']
    assert 'free' in ws.strategy.low_value_terms
    assert 'with' in ws.strategy.phrase_stopwords


def test_group_filter_limits_the_audited_storefronts(tmp_path):
    root = write_workspace(tmp_path / 'aso')
    ws = workspace.load(explicit=str(root))
    assert set(ws.config.groups()) == {'US', 'GB'}


def test_group_override_replaces_the_table(tmp_path):
    root = write_workspace(tmp_path / 'aso', config="""\
version: 1
markets:
  storefront_groups: [US]
  storefront_groups_override:
    US:
      name: United States
      locales: [en-US, fr-CA]
""")
    ws = workspace.load(explicit=str(root))
    assert ws.config.groups()['US'] == ('United States', ['en-US', 'fr-CA'])


@pytest.mark.parametrize('text, expected', [
    ('seed_keywords: [alpha, beta]', [('alpha', 5, ''), ('beta', 5, '')]),
    ('seed_keywords:\n  - [alpha, 7]', [('alpha', 7, '')]),
    ('seed_keywords:\n  - term: alpha\n    score: 3\n    why: reason',
     [('alpha', 3, 'reason')]),
])
def test_seed_keywords_accept_three_shapes(tmp_path, text, expected):
    root = write_workspace(tmp_path / 'aso', strategy=text)
    assert workspace.load(explicit=str(root)).strategy.seed_keywords == expected


@pytest.mark.parametrize('text', [
    'competitors:\n  123: Rival',
    'competitors:\n  - track_id: 123\n    label: Rival',
])
def test_competitors_accept_two_shapes(tmp_path, text):
    root = write_workspace(tmp_path / 'aso', strategy=text)
    assert workspace.load(explicit=str(root)).strategy.competitors == {123: 'Rival'}


def test_phrase_words_drop_the_stopwords(tmp_path):
    root = write_workspace(tmp_path / 'aso', strategy="""\
phrase_targets:
  - phrase: hike tracker with elevation
    score: 5
""")
    assert workspace.load(explicit=str(root)).strategy.phrase_words == {
        'hike', 'tracker', 'elevation'}


def test_require_track_id_explains_where_to_put_it(tmp_path):
    root = write_workspace(tmp_path / 'aso', config='version: 1\n')
    ws = workspace.load(explicit=str(root))
    with pytest.raises(WorkspaceError, match='track_id'):
        ws.require_track_id()


def test_environment_variable_selects_the_workspace(tmp_path, monkeypatch):
    root = write_workspace(tmp_path / 'elsewhere')
    monkeypatch.setenv('ASO_WORKSPACE', str(root))
    monkeypatch.chdir(tmp_path)
    assert workspace.load().root == root


def test_example_workspace_is_valid(example_workspace):
    assert example_workspace.config.app.name == 'Trailwise'
    assert example_workspace.strategy.brand_phrases == ['trailwise']
    assert example_workspace.strategy.notes[0][0] == 'es-mx-english-slot'
