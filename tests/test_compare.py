from aso_advisor import color, compare


def test_a_field_that_differs():
    changes = compare.diff_locales({'en-US': {'name': 'New'}}, {'en-US': {'name': 'Old'}})
    assert len(changes) == 1
    assert (changes[0].kind, changes[0].left, changes[0].right) == (
        compare.CHANGED, 'New', 'Old')


def test_a_field_that_only_the_left_side_has():
    changes = compare.diff_locales({'en-US': {'keywords': 'gps'}}, {'en-US': {}})
    assert changes[0].kind == compare.ONLY_LEFT


def test_a_field_that_only_the_right_side_has():
    changes = compare.diff_locales({'en-US': {}}, {'en-US': {'keywords': 'gps'}})
    assert changes[0].kind == compare.ONLY_RIGHT


def test_equal_values_make_no_change():
    assert compare.diff_locales({'en-US': {'name': 'A'}}, {'en-US': {'name': 'A'}}) == []


def test_an_empty_value_equals_a_missing_value():
    assert compare.diff_locales({'en-US': {'subtitle': ''}}, {'en-US': {}}) == []


def test_a_locale_that_only_one_side_has():
    changes = compare.diff_locales({'de-DE': {'name': 'Neu'}}, {})
    assert changes[0].locale == 'de-DE'


def test_the_field_filter():
    changes = compare.diff_locales({'en-US': {'name': 'A', 'keywords': 'b'}},
                                   {'en-US': {'name': 'B', 'keywords': 'c'}},
                                   fields={'name'})
    assert [c.field for c in changes] == ['name']


def test_the_order_puts_the_name_before_the_description():
    changes = compare.diff_locales(
        {'en-US': {'description': 'a', 'name': 'b', 'keywords': 'c'}}, {'en-US': {}})
    assert [c.field for c in changes] == ['name', 'keywords', 'description']


def test_summarize_counts_locales_and_fields():
    changes = compare.diff_locales(
        {'en-US': {'name': 'a', 'keywords': 'b'}, 'de-DE': {'name': 'c'}}, {})
    assert compare.summarize(changes) == (2, 3)


def test_shorten_keeps_one_line():
    assert compare.shorten('one\ntwo   three', 40) == 'one two three'
    assert compare.shorten('x' * 80, 10) == 'x' * 9 + '…'


def test_the_lines_name_both_sides():
    changes = compare.diff_locales({'en-US': {'name': 'New'}}, {'en-US': {'name': 'Old'}})
    lines = compare.format_changes(changes, 'yours', 'store')
    assert lines[0] == '[en-US]'
    assert any('- store Old' in line for line in lines)
    assert any('+ yours New' in line for line in lines)


# -- colour -------------------------------------------------------------------

def test_no_color_switches_colour_off(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    assert color.paint('text', 'red') == 'text'


def test_force_color_switches_colour_on(monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('FORCE_COLOR', '1')
    assert color.paint('text', 'red') == '\033[31mtext\033[0m'


def test_a_pipe_gets_no_colour(monkeypatch):
    monkeypatch.delenv('FORCE_COLOR', raising=False)
    monkeypatch.delenv('NO_COLOR', raising=False)
    assert color.paint('text', 'red') == 'text'      # pytest captures the output


def test_an_unknown_colour_changes_nothing(monkeypatch):
    monkeypatch.setenv('FORCE_COLOR', '1')
    assert color.paint('text', 'chartreuse') == 'text'


def test_each_severity_has_a_colour(monkeypatch):
    monkeypatch.setenv('FORCE_COLOR', '1')
    assert color.severity('CRITICAL').startswith('\033[31m')
    assert color.severity('HIGH', 'text').endswith('text\033[0m')
