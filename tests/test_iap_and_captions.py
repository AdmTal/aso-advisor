"""Tests for the in-app purchase rules and the screenshot caption rules."""

from aso_advisor import assets, loader, rules
from aso_advisor.model import LocaleMeta
from aso_advisor.workspace import AssetSettings, Strategy
from conftest import context, png_bytes

IAP_YAML = """\
locales:
  en-US:
    language: English
    name: 'Trailwise: Hike GPS'
    subtitle: Offline Maps
    keywords: compass,elevation
in_app_purchases:
  - product_id: com.example.pro
    reference_name: Pro unlock
    locales:
      en-US:
        name: Offline Park Packs
        description: Download a whole park and walk with no signal at all.
"""


def only(found, rule):
    return [s for s in found if s.rule == rule]


def product(name='Offline Park Packs', description='Short.', code='en-US',
            product_id='com.example.pro'):
    return {'product_id': product_id, 'reference_name': '',
            'locales': {code: {'name': name, 'description': description}}}


def meta(code='en-US', **fields):
    return LocaleMeta(code=code, **fields)


# -- reading ------------------------------------------------------------------

def test_load_the_in_app_purchases_of_a_version(tmp_path):
    directory = tmp_path / '1.0'
    directory.mkdir()
    (directory / 'metadata.yaml').write_text(IAP_YAML, encoding='utf-8')
    products = loader.load_iap(directory)
    assert len(products) == 1
    assert products[0]['product_id'] == 'com.example.pro'
    assert products[0]['locales']['en-US']['name'] == 'Offline Park Packs'


def test_a_version_without_in_app_purchases(tmp_path):
    directory = tmp_path / '1.0'
    directory.mkdir()
    (directory / 'm.yaml').write_text('locales:\n  en-US:\n    name: A\n')
    assert loader.load_iap(directory) == []


def test_the_mapping_shape_also_works(tmp_path):
    directory = tmp_path / '1.0'
    directory.mkdir()
    (directory / 'm.yaml').write_text(
        'locales:\n  en-US:\n    name: A\n'
        'in_app_purchases:\n  com.example.pro:\n    locales:\n      en-US:\n'
        '        name: Pro\n', encoding='utf-8')
    products = loader.load_iap(directory)
    assert products[0]['product_id'] == 'com.example.pro'


# -- the rules ----------------------------------------------------------------

def test_a_name_that_is_too_long_is_critical():
    ctx = context({'en-US': meta()}, iap=[product(name='x' * 31)])
    found = only(rules.check_iap_limits(ctx), 'IAP_LIMIT')
    assert found and found[0].severity == 'CRITICAL'
    assert '31/30' in found[0].title


def test_a_description_that_is_too_long():
    ctx = context({'en-US': meta()}, iap=[product(description='x' * 46)])
    assert only(rules.check_iap_limits(ctx), 'IAP_LIMIT')


def test_a_name_of_the_correct_length_passes():
    ctx = context({'en-US': meta()}, iap=[product(name='x' * 30, description='y' * 45)])
    assert rules.check_iap_limits(ctx) == []


def test_a_name_that_adds_no_new_word():
    ctx = context({'en-US': meta(name='Trailwise Offline', keywords='maps,gps')},
                  iap=[product(name='Offline Maps')])
    found = only(rules.check_iap_duplicates(ctx), 'IAP_DUP')
    assert found and found[0].severity == 'MEDIUM'


def test_a_name_that_brings_a_new_word_is_fine():
    ctx = context({'en-US': meta(name='Trailwise', keywords='maps')},
                  iap=[product(name='Offline Park Packs')])
    assert rules.check_iap_duplicates(ctx) == []


def test_a_product_that_is_not_localized_everywhere():
    ctx = context({'en-US': meta(name='A'), 'de-DE': meta(code='de-DE', name='B')},
                  iap=[product()])
    found = only(rules.check_iap_locales(ctx), 'IAP_LOCALE')
    assert found and 'de-DE' in found[0].title


def test_a_product_that_is_localized_everywhere():
    ctx = context({'en-US': meta(name='A')}, iap=[product()])
    assert rules.check_iap_locales(ctx) == []


def test_the_seed_opportunity_needs_a_product():
    strategy = Strategy(seed_keywords=[('offline', 9, 'why')])
    without = context({'en-US': meta(keywords='maps')}, strategy=strategy)
    assert rules.check_iap_opportunities(without) == []

    with_product = context({'en-US': meta(keywords='maps')}, strategy=strategy,
                           iap=[product()])
    found = only(rules.check_iap_opportunities(with_product), 'IAP_SEED')
    assert found and 'offline' in found[0].title


def test_the_rules_run_in_the_whole_audit():
    ctx = context({'en-US': meta(name='Trailwise Offline', keywords='maps')},
                  iap=[product(name='Offline Maps', description='x' * 46)])
    found = {s.rule for s in rules.run_all(ctx)}
    assert 'IAP_LIMIT' in found and 'IAP_DUP' in found


# -- captions -----------------------------------------------------------------

def shot(root, locale, device, name):
    path = root / locale / 'screenshots' / device / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes(1320, 2868))
    return path


def captions(root, text):
    (root / assets.CAPTIONS_FILE).write_text(text, encoding='utf-8')


def settings(**fields):
    return AssetSettings(required_locales=['en-US'], **fields)


def audit(root, phrase_words=()):
    return assets.audit(root, {'en-US': LocaleMeta(code='en-US')}, settings(),
                        phrase_words=phrase_words)


def rules_of(found):
    return sorted({s.rule for s in found})


def test_no_caption_file_means_no_caption_finding(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    assert audit(tmp_path) == []


def test_a_locale_that_the_caption_file_forgets(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    captions(tmp_path, 'locales:\n  de-DE:\n    - Eine Aufnahme\n')
    assert 'CAPTION_MISSING' in rules_of(audit(tmp_path))


def test_a_caption_that_is_too_long(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    captions(tmp_path, 'locales:\n  en-US:\n    - ' + 'word ' * 20 + '\n')
    assert 'CAPTION_LONG' in rules_of(audit(tmp_path))


def test_the_number_of_captions_and_screenshots_must_match(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'iphone-6.9', '02.png')
    captions(tmp_path, 'locales:\n  en-US:\n    - Only one caption\n')
    assert 'CAPTION_COUNT' in rules_of(audit(tmp_path))


def test_captions_per_device(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    captions(tmp_path, 'locales:\n  en-US:\n    iphone-6.9:\n      - Offline hiking maps\n')
    assert audit(tmp_path, phrase_words={'offline', 'hiking'}) == []


def test_a_caption_without_a_target_word(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    captions(tmp_path, 'locales:\n  en-US:\n    - Beautiful design\n')
    found = audit(tmp_path, phrase_words={'offline', 'hiking', 'maps'})
    assert 'CAPTION_KEYWORDS' in rules_of(found)
    assert [s for s in found if s.rule == 'CAPTION_KEYWORDS'][0].severity == 'MEDIUM'


def test_a_caption_with_a_target_word(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    captions(tmp_path, 'locales:\n  en-US:\n    - Offline maps for the whole park\n')
    assert 'CAPTION_KEYWORDS' not in rules_of(
        audit(tmp_path, phrase_words={'offline', 'hiking'}))


def test_the_caption_file_is_not_read_as_a_locale(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    captions(tmp_path, 'locales:\n  en-US:\n    - Offline maps\n')
    assert 'captions.yaml' not in assets.scan(tmp_path)
