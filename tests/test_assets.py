from aso_advisor import assets
from aso_advisor.model import LocaleMeta
from aso_advisor.workspace import AssetSettings
from conftest import mp4_bytes, png_bytes


def settings(**fields):
    return AssetSettings(required_locales=['en-US'], **fields)


def shot(root, locale, device, name, width=1320, height=2868, alpha=False):
    path = root / locale / 'screenshots' / device / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes(width, height, alpha=alpha))
    return path


def preview(root, locale, device, name, seconds=20):
    path = root / locale / 'previews' / device / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mp4_bytes(seconds))
    return path


def rules_of(found):
    return sorted({s.rule for s in found})


# -- readers ------------------------------------------------------------------

def test_png_reader(tmp_path):
    path = tmp_path / 'a.png'
    path.write_bytes(png_bytes(320, 480))
    assert assets.image_info(path) == (320, 480, False)


def test_png_reader_finds_the_alpha_channel(tmp_path):
    path = tmp_path / 'a.png'
    path.write_bytes(png_bytes(320, 480, alpha=True))
    assert assets.image_info(path)[2] is True


def test_readers_return_none_for_a_file_that_is_not_an_image(tmp_path):
    path = tmp_path / 'a.png'
    path.write_bytes(b'not a png at all, really not')
    assert assets.image_info(path) is None


def test_mp4_duration(tmp_path):
    path = tmp_path / 'a.mp4'
    path.write_bytes(mp4_bytes(22.5))
    assert abs(assets.mp4_duration(path) - 22.5) < 0.01


def test_mp4_duration_of_a_broken_file(tmp_path):
    path = tmp_path / 'a.mp4'
    path.write_bytes(b'\x00\x00\x00\x08free')
    assert assets.mp4_duration(path) is None


def test_normalize_device():
    assert assets.normalize_device('iPhone 6.9') == 'iphone-6.9'
    assert assets.normalize_device('  iPad__13 ') == 'ipad-13'


# -- the tree -----------------------------------------------------------------

def test_scan_reads_locales_devices_and_kinds(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'ipad-13', '01.png', 2064, 2752)
    preview(tmp_path, 'en-US', 'iphone-6.9', '01.mp4')
    tree = assets.scan(tmp_path)
    assert set(tree['en-US']['screenshots']) == {'iphone-6.9', 'ipad-13'}
    assert len(tree['en-US']['previews']['iphone-6.9']) == 1


def test_scan_of_a_missing_directory(tmp_path):
    assert assets.scan(tmp_path / 'nothing') == {}


def test_summary_counts_the_files(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'iphone-6.9', '02.png')
    assert assets.summary(tmp_path) == [('en-US', 'screenshots', 'iphone-6.9', 2)]


# -- audit --------------------------------------------------------------------

def test_clean_tree_has_no_finding(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'iphone-6.9', '02.png')
    preview(tmp_path, 'en-US', 'iphone-6.9', '01.mp4', seconds=20)
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert found == []


def test_required_locale_without_screenshots(tmp_path):
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert rules_of(found) == ['ASSET_MISSING']


def test_wrong_pixel_size(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png', 1242, 2688)
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert rules_of(found) == ['ASSET_SIZE']
    assert found[0].severity == 'HIGH'


def test_landscape_size_is_accepted(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png', 2868, 1320)
    assert assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings()) == []


def test_alpha_channel_is_reported(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png', alpha=True)
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert 'ASSET_ALPHA' in rules_of(found)


def test_too_many_screenshots_is_critical(tmp_path):
    for index in range(11):
        shot(tmp_path, 'en-US', 'iphone-6.9', f'{index:02d}.png')
    found = [s for s in assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
             if s.rule == 'ASSET_COUNT']
    assert found[0].severity == 'CRITICAL'


def test_preview_outside_the_accepted_length(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    preview(tmp_path, 'en-US', 'iphone-6.9', '01.mp4', seconds=42)
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert rules_of(found) == ['ASSET_VIDEO_LENGTH']


def test_unknown_device_directory(tmp_path):
    shot(tmp_path, 'en-US', 'phone', '01.png')
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert 'ASSET_DEVICE' in rules_of(found)


def test_files_without_a_numeric_prefix(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', 'hero.png')
    shot(tmp_path, 'en-US', 'iphone-6.9', 'features.png')
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert 'ASSET_ORDER' in rules_of(found)


def test_locale_directory_without_metadata(tmp_path):
    shot(tmp_path, 'fr-FR', 'iphone-6.9', '01.png')
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png')
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')}, settings())
    assert 'ASSET_ORPHAN' in rules_of(found)


def test_dimension_check_can_be_switched_off(tmp_path):
    shot(tmp_path, 'en-US', 'iphone-6.9', '01.png', 100, 100)
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')},
                         settings(check_dimensions=False))
    assert found == []


def test_extra_device_sizes_from_the_configuration(tmp_path):
    shot(tmp_path, 'en-US', 'watch-ultra', '01.png', 410, 502)
    found = assets.audit(tmp_path, {'en-US': LocaleMeta(code='en-US')},
                         settings(device_sizes={'watch-ultra': [(410, 502)]}))
    assert found == []
