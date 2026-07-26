import json

from aso_advisor import report
from aso_advisor.model import LocaleMeta, Suggestion
from aso_advisor.workspace import Strategy
from conftest import context

STATS = {'open': 1, 'new': 1, 'regressed': 0, 'resolved': []}


def sample_context():
    return context(
        {'en-US': LocaleMeta(code='en-US', name='Trailwise', keywords='gps,map')},
        strategy=Strategy(phrase_targets=[('offline maps', 8, '')],
                          seed_keywords=[('offline', 9, 'why')]),
        version='2.1')


def test_report_file_name_holds_a_unix_timestamp(tmp_path):
    path = report.write_report('# body', tmp_path, timestamp=1753574400)
    assert path.name == 'aso-report-1753574400.md'
    assert path.read_text(encoding='utf-8') == '# body'


def test_two_reports_in_the_same_second_do_not_overwrite(tmp_path):
    first = report.write_report('# one', tmp_path, timestamp=1753574400)
    second = report.write_report('# two', tmp_path, timestamp=1753574400)
    assert first != second
    assert first.read_text(encoding='utf-8') == '# one'
    assert second.name == 'aso-report-1753574400-2.md'


def test_markdown_holds_the_header_the_table_and_the_actions():
    found = [Suggestion('EMPTY', 'en-US:subtitle', 'en-US', 'HIGH', 'the subtitle is empty',
                        fix='write one')]
    found[0].is_new = True
    body = report.render_markdown(sample_context(), 7, found, STATS, app_name='Trailwise',
                                  timestamp=1753574400)
    assert 'ASO Advisor report — Trailwise metadata 2.1' in body
    assert 'Run #7' in body
    assert '`1753574400`' in body
    assert '**[NEW]**' in body
    assert 'the subtitle is empty' in body
    assert '👉 _Fix: write one_' in body


def test_markdown_holds_the_coverage_matrix_and_the_proposals():
    body = report.render_markdown(sample_context(), 1, [], STATS, timestamp=1)
    assert 'Long-tail phrase coverage per storefront' in body
    assert 'offline maps (8)' in body
    assert 'Proposed keyword fields' in body
    assert '+ gps,map,offline' in body


def test_markdown_says_when_nothing_is_open():
    body = report.render_markdown(sample_context(), 1, [],
                                  {'open': 0, 'new': 0, 'regressed': 0, 'resolved': []},
                                  timestamp=1)
    assert 'Nothing is open' in body


def test_markdown_lists_the_resolved_items():
    stats = {'open': 0, 'new': 0, 'regressed': 0,
             'resolved': [{'fid': 'S-1', 'title': 'the old problem'}]}
    body = report.render_markdown(sample_context(), 2, [], stats, timestamp=1)
    assert '~~the old problem~~' in body


def test_markdown_holds_the_rank_table():
    rows = [{'term': 'hiking maps', 'country': 'us', 'rank': 12, 'prev': 40,
             'ts': '2026-07-26 10:00:00Z', 'prev_ts': ''}]
    body = report.render_markdown(sample_context(), 1, [], STATS, rank_rows=rows, timestamp=1)
    assert '| hiking maps | us | #12 | #40 | 2026-07-26 |' in body


def test_markdown_holds_the_asset_table():
    body = report.render_markdown(sample_context(), 1, [], STATS,
                                  asset_rows=[('en-US', 'screenshots', 'iphone-6.9', 3)],
                                  timestamp=1)
    assert '| en-US | screenshots | iphone-6.9 | 3 |' in body


def test_json_output_is_machine_readable():
    found = [Suggestion('EMPTY', 'k', 'en-US', 'HIGH', 'a title')]
    data = json.loads(report.render_json(sample_context(), 3, found, STATS,
                                         app_name='Trailwise', timestamp=1753574400))
    assert data['app'] == 'Trailwise'
    assert data['metadata_version'] == '2.1'
    assert data['run'] == 3
    assert data['timestamp'] == 1753574400
    assert data['counts']['HIGH'] == 1
    assert data['suggestions'][0]['id'] == found[0].fid


def test_console_output_names_the_report(capsys, tmp_path):
    found = [Suggestion('LIMIT', 'k', 'en-US', 'CRITICAL', 'too long', fix='cut it')]
    report.print_console(sample_context(), 4, found, STATS, tmp_path / 'r.md')
    printed = capsys.readouterr().out
    assert 'run #4' in printed
    assert 'too long' in printed
    assert '→ cut it' in printed
    assert 'r.md' in printed
