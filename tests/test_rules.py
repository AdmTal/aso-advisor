from aso_advisor import rules
from aso_advisor.model import LocaleMeta
from aso_advisor.workspace import Strategy
from conftest import context, rule_ids


def meta(code='en-US', **fields):
    return LocaleMeta(code=code, **fields)


def only(found, rule):
    return [s for s in found if s.rule == rule]


# -- hard limits --------------------------------------------------------------

def test_limit_rule_is_critical():
    ctx = context({'en-US': meta(name='x' * 31)})
    found = only(rules.check_limits(ctx), 'LIMIT')
    assert len(found) == 1
    assert found[0].severity == 'CRITICAL'
    assert '31/30' in found[0].title


def test_limit_rule_accepts_the_exact_maximum():
    assert rules.check_limits(context({'en-US': meta(name='x' * 30)})) == []


# -- format and budget --------------------------------------------------------

def test_format_finds_spaces_and_trailing_comma():
    ctx = context({'en-US': meta(keywords='one, two,')})
    assert len(rules.check_format(ctx)) == 2


def test_empty_fields_are_high():
    ctx = context({'en-US': meta(name='Trailwise')})
    found = rules.check_empty_fields(ctx)
    assert {s.severity for s in found} == {'HIGH'}
    assert len(found) == 2      # The subtitle and the keyword field.


def test_empty_rule_is_quiet_for_a_description_only_locale():
    ctx = context({'en-US': meta(description='text')})
    assert rules.check_empty_fields(ctx) == []


def test_budget_reports_unused_keyword_characters():
    ctx = context({'en-US': meta(keywords='short')})
    found = only(rules.check_budget(ctx), 'BUDGET')
    assert '95 unused keyword characters' in found[0].title


# -- duplicates ---------------------------------------------------------------

def test_duplicate_entries_in_one_field():
    ctx = context({'en-US': meta(keywords='map,gps,Map')})
    assert only(rules.check_duplicates_in_field(ctx), 'DUP_FIELD')


def test_keyword_that_the_own_title_already_has():
    ctx = context({'en-US': meta(name='Trailwise GPS', keywords='gps,compass')})
    found = only(rules.check_duplicates_vs_title(ctx), 'DUP_TITLE')
    assert 'gps' in found[0].title


def test_non_spaced_locale_uses_substring_comparison():
    ctx = context({'ja': meta(code='ja', name='登山地図とGPS', keywords='地図,コンパス')})
    found = only(rules.check_duplicates_vs_title(ctx), 'DUP_TITLE')
    assert '地図' in found[0].title


def test_word_in_both_title_and_subtitle():
    ctx = context({'en-US': meta(name='Trail Maps', subtitle='Offline Trail GPS')})
    found = only(rules.check_title_subtitle_overlap(ctx), 'TITLE_SUB_DUP')
    assert 'trail' in found[0].title


def test_multi_word_keyword_entry():
    ctx = context({'en-US': meta(keywords='offline maps,gps')})
    assert only(rules.check_multiword_entries(ctx), 'MULTIWORD')


def test_singular_and_plural_pair():
    ctx = context({'en-US': meta(keywords='path,paths,gps')})
    found = only(rules.check_plural_pairs(ctx), 'PLURAL')
    assert 'path/paths' in found[0].title


# -- cross-localization -------------------------------------------------------

def test_same_word_in_two_cross_indexed_keyword_fields():
    ctx = context({'en-US': meta(keywords='offline,gps'),
                   'es-MX': meta(code='es-MX', keywords='offline,trail')})
    found = only(rules.check_cross_locale_duplicates(ctx), 'DUP_XLOC')
    assert 'offline' in found[0].title
    assert found[0].scope == 'US'


def test_cross_locale_overlap_is_structural_when_needed_elsewhere():
    # en-US is the only carrier of "gps" for the United States, and en-GB is
    # the only carrier for Germany. The overlap in the United Kingdom, where
    # both index, is structural. Neither locale can remove the word.
    groups = {'US': ('United States', ['en-US', 'es-MX']),
              'GB': ('United Kingdom', ['en-GB', 'en-US']),
              'DE': ('Germany', ['de-DE', 'en-GB'])}
    ctx = context({'en-US': meta(keywords='gps'), 'en-GB': meta(code='en-GB', keywords='gps'),
                   'de-DE': meta(code='de-DE', keywords='karte')}, groups=groups)
    found = rules.check_cross_locale_duplicates(ctx)
    assert rule_ids(found) == ['DUP_XLOC_STRUCT']


def test_cross_locale_duplicate_names_the_locale_that_drops_the_word():
    # en-US covers the United Kingdom storefront as well, so en-GB is the one
    # that must free the slot.
    ctx = context({'en-US': meta(keywords='gps'), 'en-GB': meta(code='en-GB', keywords='gps')})
    found = only(rules.check_cross_locale_duplicates(ctx), 'DUP_XLOC')
    assert 'remove from en-GB' in found[0].fix


def test_keyword_supplied_free_by_a_cross_indexed_title():
    ctx = context({'en-US': meta(name='Trailwise Hike GPS'),
                   'es-MX': meta(code='es-MX', keywords='hike,mapa')})
    found = only(rules.check_keywords_vs_group_titles(ctx), 'DEAD_TITLE')
    assert 'hike' in found[0].title
    assert found[0].scope == 'es-MX'


def test_dead_title_keeps_a_word_that_a_phrase_needs():
    strategy = Strategy(phrase_targets=[('hike map', 8, '')])
    ctx = context({'en-US': meta(name='Trailwise Hike'),
                   'es-MX': meta(code='es-MX', keywords='hike,map')},
                  strategy=strategy)
    # "hike" completes "hike map" inside es-MX, so the rule leaves it alone.
    assert rules.check_keywords_vs_group_titles(ctx) == []


# -- term quality -------------------------------------------------------------

def test_low_value_terms_come_from_the_strategy():
    strategy = Strategy(low_value_terms={'free'})
    ctx = context({'en-US': meta(keywords='free,gps')}, strategy=strategy)
    found = only(rules.check_low_value_terms(ctx), 'LOWVALUE')
    assert 'free' in found[0].title


def test_trademarks_are_reported_as_a_note():
    strategy = Strategy(trademark_terms={'rivalapp'}, soft_trademark_terms={'stories'})
    ctx = context({'en-US': meta(keywords='rivalapp,stories')}, strategy=strategy)
    found = rules.check_trademarks(ctx)
    assert {s.rule for s in found} == {'TRADEMARK', 'TRADEMARK_SOFT'}
    assert all(s.severity == 'INFO' for s in found)


# -- brand and phrases --------------------------------------------------------

def test_brand_coverage_needs_every_word_in_one_localization():
    strategy = Strategy(brand_phrases=['trail wise'])
    covered = context({'en-US': meta(name='Trail Wise')}, strategy=strategy)
    assert rules.check_brand_coverage(covered) == []

    split = context({'en-US': meta(name='Trail'), 'en-GB': meta(code='en-GB', name='Wise')},
                    strategy=strategy)
    found = only(rules.check_brand_coverage(split), 'BRAND')
    assert found and found[0].severity == 'HIGH'


def test_brand_rule_is_quiet_without_brand_phrases():
    assert rules.check_brand_coverage(context({'en-US': meta(name='Anything')})) == []


def test_phrase_words_must_share_one_localization():
    strategy = Strategy(phrase_targets=[('offline hiking maps', 9, '')])
    # The three words exist in the group, but in two different localizations.
    split = context({'en-US': meta(keywords='offline,maps'),
                     'es-MX': meta(code='es-MX', keywords='hiking')}, strategy=strategy)
    found = only(rules.check_phrase_coverage(split), 'PHRASE')
    assert found and 'hiking' in found[0].detail

    together = context({'en-US': meta(keywords='offline,hiking,maps')}, strategy=strategy)
    assert rules.check_phrase_coverage(together) == []


def test_phrase_stopwords_do_not_need_a_slot():
    strategy = Strategy(phrase_targets=[('hike with elevation', 9, '')])
    ctx = context({'en-US': meta(keywords='hike,elevation')}, strategy=strategy)
    assert rules.check_phrase_coverage(ctx) == []


def test_low_score_phrases_do_not_make_suggestions():
    strategy = Strategy(phrase_targets=[('rare query', 2, '')])
    assert rules.check_phrase_coverage(context({'en-US': meta()}, strategy=strategy)) == []


# -- seeds --------------------------------------------------------------------

def test_uncovered_seed_keywords():
    strategy = Strategy(seed_keywords=[('offline', 9, 'why'), ('gps', 3, 'low score')])
    ctx = context({'en-US': meta(keywords='maps')}, strategy=strategy)
    found = only(rules.check_seed_opportunities(ctx), 'SEED')
    assert len(found) == 1                       # The score of "gps" is below 5.
    assert 'offline' in found[0].title


def test_seed_is_covered_by_any_localization_of_the_group():
    strategy = Strategy(seed_keywords=[('offline', 9, 'why')])
    ctx = context({'en-US': meta(), 'es-MX': meta(code='es-MX', keywords='offline')},
                  strategy=strategy)
    assert rules.check_seed_opportunities(ctx) == []


# -- conversion and coverage --------------------------------------------------

def test_promotional_text_rules():
    ctx = context({'en-US': meta(description='text'),
                   'en-GB': meta(code='en-GB', description='text', promotional_text='short')})
    found = only(rules.check_conversion_fields(ctx), 'PROMO')
    assert {s.severity for s in found} == {'MEDIUM', 'LOW'}


def test_description_depth_compares_structure_not_length():
    full = 'One.\n\nTwo.\n\nThree.\n\n• a\n• b'
    ctx = context({'en-US': meta(description=full),
                   'de-DE': meta(code='de-DE', description='Eins.\n\nZwei.')})
    found = only(rules.check_description_depth(ctx), 'DESC_DEPTH')
    assert found and found[0].scope == 'de-DE'


def test_ai_tag_alignment_reads_the_opening():
    strategy = Strategy(ai_tag_terms=['hike', 'map', 'offline', 'gps'])
    ctx = context({'en-US': meta(description='A beautiful companion for your journeys.')},
                  strategy=strategy)
    assert only(rules.check_description_ai_alignment(ctx), 'AI_TAGS')

    good = context({'en-US': meta(description='An offline hike map with gps.')},
                   strategy=strategy)
    assert rules.check_description_ai_alignment(good) == []


def test_locale_priority_drives_the_coverage_rule():
    strategy = Strategy(locale_priority={'fr-FR': 'France'})
    ctx = context({'en-US': meta()}, strategy=strategy)
    found = only(rules.check_locale_coverage(ctx), 'LOCALE')
    assert found and 'fr-FR' in found[0].title


# -- version differences ------------------------------------------------------

def test_changelog_lists_the_changes():
    ctx = context({'en-US': meta(name='New Name', keywords='gps,offline')},
                  prev_locales={'en-US': meta(name='Old Name', keywords='gps')},
                  version='2.1', prev_version='2.0')
    found = only(rules.check_changelog(ctx), 'DIFF')
    assert 'Old Name' in found[0].detail
    assert '+offline' in found[0].detail


def test_changelog_is_quiet_without_a_previous_version():
    assert rules.check_changelog(context({'en-US': meta(name='A')})) == []


# -- the whole run ------------------------------------------------------------

def test_run_all_sorts_by_severity_and_respects_disabled_rules():
    ctx = context({'en-US': meta(name='x' * 31, keywords='free, free,')})
    found = rules.run_all(ctx)
    assert found[0].severity == 'CRITICAL'
    assert 'LIMIT' in rule_ids(found)
    assert 'LIMIT' not in rule_ids(rules.run_all(ctx, disabled={'LIMIT'}))


def test_proposed_keyword_lines_fill_the_free_characters():
    strategy = Strategy(seed_keywords=[('offline', 9, ''), ('elevation', 8, '')])
    ctx = context({'en-US': meta(keywords='gps,maps')}, strategy=strategy)
    proposals = rules.propose_keyword_lines(ctx)
    assert proposals[0][0] == 'en-US'
    assert 'offline' in proposals[0][2]
    assert proposals[0][3] == ['+offline', '+elevation']


def test_proposals_never_go_over_the_limit():
    strategy = Strategy(seed_keywords=[(f'term{i}', 9, '') for i in range(40)])
    ctx = context({'en-US': meta(keywords='gps')}, strategy=strategy)
    _code, _old, new, _changed = rules.propose_keyword_lines(ctx)[0]
    assert len(new) <= 100


def test_primary_group_follows_the_default_country():
    ctx = context({'en-US': meta()}, default_country='gb')
    assert ctx.primary_group == 'GB'
