from aso_advisor.model import LocaleMeta, Suggestion, keyword_entries, tokens


def test_tokens_split_on_punctuation_and_lowercase():
    assert tokens('Hike & Trail GPS') == ['hike', 'trail', 'gps']
    assert tokens('') == []
    assert tokens(None) == []


def test_tokens_keep_combining_marks_together():
    # A tokenizer built on \w breaks Devanagari into single consonants.
    assert tokens('स्क्रीन रिकॉर्डर') == ['स्क्रीन', 'रिकॉर्डर']


def test_keyword_entries_trim_and_drop_empty():
    assert keyword_entries('a, b ,,c\nd,') == ['a', 'b', 'c', 'd']
    assert keyword_entries('') == []


def test_indexed_tokens_join_all_fields_and_implicit_words():
    meta = LocaleMeta(code='en-US', name='Trailwise Hike', subtitle='Offline Maps',
                      keywords='gps,compass')
    assert meta.indexed_tokens == {'trailwise', 'hike', 'offline', 'maps', 'gps',
                                   'compass', 'app', 'apps'}


def test_non_spaced_locale_flag():
    assert LocaleMeta(code='ja').is_non_spaced
    assert not LocaleMeta(code='en-US').is_non_spaced


def test_fingerprint_is_stable_and_specific():
    first = Suggestion('DUP_TITLE', 'gps', 'en-US', 'HIGH', 'title one')
    same = Suggestion('DUP_TITLE', 'gps', 'en-US', 'HIGH', 'a different title')
    other_scope = Suggestion('DUP_TITLE', 'gps', 'de-DE', 'HIGH', 'title one')
    assert first.fid == same.fid          # The wording of the title may change.
    assert first.fid != other_scope.fid   # The scope may not.
    assert first.fid.startswith('S-') and len(first.fid) == 10


def test_severity_rank_orders_critical_first():
    critical = Suggestion('LIMIT', 'k', 'global', 'CRITICAL', 't')
    info = Suggestion('DIFF', 'k', 'global', 'INFO', 't')
    assert critical.severity_rank < info.severity_rank
