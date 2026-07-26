"""App Store storefront reference data.

Three tables live here:

STOREFRONT_GROUPS
    Cross-localization. In each storefront, the App Store indexes the metadata
    of more than one localization. A word in any localization of the group
    makes the app findable in that storefront. A search phrase, however, is
    made only from the words of ONE localization. The tool uses this table for
    almost every keyword rule, so you can replace it in your workspace
    configuration if Apple changes the groups.

ASC_LOCALES
    All locale codes that App Store Connect accepts.

STOREFRONT_IDS
    The numeric storefront identifier for the autocomplete endpoint.

Apple does not publish the group table. The values below come from the public
ASO research that the documentation lists in `docs/concepts.md`. Use the
`aso verify-groups` command to test a group against the live store.
"""

# Storefront group -> (human name, localizations indexed in that storefront).
# The first locale in each list is the local language of the storefront.
STOREFRONT_GROUPS = {
    'US': ('United States', ['en-US', 'es-MX', 'ru', 'ar-SA', 'vi']),
    'GB': ('United Kingdom', ['en-GB', 'en-US']),
    'AU': ('Australia', ['en-AU', 'en-GB', 'en-US']),
    'CA': ('Canada', ['en-CA', 'fr-CA', 'en-US']),
    'IN': ('India', ['hi', 'en-GB']),
    'MY': ('Malaysia', ['ms', 'en-GB']),
    'SE': ('Sweden', ['sv', 'en-GB']),
    'DK': ('Denmark', ['da', 'en-GB']),
    'PT': ('Portugal', ['pt-PT', 'en-GB']),
    'DE': ('Germany', ['de-DE', 'en-GB']),
    'FR': ('France', ['fr-FR', 'en-GB']),
    'ES': ('Spain', ['es-ES', 'en-GB']),
    'IT': ('Italy', ['it', 'en-GB']),
    'NL': ('Netherlands', ['nl-NL', 'en-GB']),
    'JP': ('Japan', ['ja', 'en-US']),
    'KR': ('Korea', ['ko', 'en-US']),
    'BR': ('Brazil', ['pt-BR', 'en-US']),
    'MX': ('Mexico', ['es-MX', 'en-US']),
    'PL': ('Poland', ['pl', 'en-GB']),
    'TR': ('Turkey', ['tr', 'en-GB']),
    'TH': ('Thailand', ['th', 'en-GB']),
    'ID': ('Indonesia', ['id', 'en-GB']),
    'UA': ('Ukraine', ['uk', 'en-GB']),
    'CN': ('China mainland', ['zh-Hans', 'en-GB']),
    'TW': ('Taiwan', ['zh-Hant', 'en-GB']),
    'HK': ('Hong Kong', ['zh-Hant', 'zh-Hans', 'en-GB']),
    'CZ': ('Czechia', ['cs', 'en-GB']),
    'GR': ('Greece', ['el', 'en-GB']),
    'FI': ('Finland', ['fi', 'en-GB']),
    'IL': ('Israel', ['he', 'en-GB']),
    'HR': ('Croatia', ['hr', 'en-GB']),
    'HU': ('Hungary', ['hu', 'en-GB']),
    'NO': ('Norway', ['no', 'en-GB']),
    'RO': ('Romania', ['ro', 'en-GB']),
    'SK': ('Slovakia', ['sk', 'en-GB']),
}

# Every locale code that App Store Connect accepts, for the coverage rule.
ASC_LOCALES = [
    'ar-SA', 'ca', 'cs', 'da', 'de-DE', 'el', 'en-AU', 'en-CA', 'en-GB',
    'en-US', 'es-ES', 'es-MX', 'fi', 'fr-CA', 'fr-FR', 'he', 'hi', 'hr',
    'hu', 'id', 'it', 'ja', 'ko', 'ms', 'nl-NL', 'no', 'pl', 'pt-BR',
    'pt-PT', 'ro', 'ru', 'sk', 'sv', 'th', 'tr', 'uk', 'vi',
    'zh-Hans', 'zh-Hant',
]

# Country code -> storefront identifier. The autocomplete endpoint needs it in
# the X-Apple-Store-Front header.
STOREFRONT_IDS = {
    'us': 143441, 'gb': 143444, 'au': 143460, 'ca': 143455,
    'de': 143443, 'fr': 143442, 'es': 143454, 'it': 143450,
    'jp': 143462, 'kr': 143466, 'br': 143503, 'mx': 143468,
    'ru': 143469, 'in': 143467, 'nl': 143452, 'sa': 143479,
    'vn': 143471, 'tr': 143480, 'id': 143476, 'my': 143473,
    'se': 143456, 'dk': 143458, 'pt': 143453, 'no': 143457,
    'fi': 143447, 'pl': 143478, 'th': 143475, 'ua': 143492,
    'cz': 143489, 'gr': 143448, 'il': 143491, 'hr': 143494,
    'hu': 143482, 'ro': 143487, 'sk': 143496,
    'cn': 143465, 'tw': 143470, 'hk': 143463,
    'ie': 143449, 'nz': 143461, 'za': 143472, 'ch': 143459,
    'at': 143445, 'be': 143446, 'ph': 143474, 'sg': 143464,
    'ae': 143481, 'ng': 143561, 'eg': 143516, 'pk': 143477,
}

# Locales that write without spaces between words. Token rules fall back to
# substring comparison for them.
NON_SPACED_LOCALES = {'zh-Hans', 'zh-Hant', 'ja', 'th'}


def group_of_country(country):
    """Storefront group identifier for an iTunes country code, or None."""
    gid = (country or '').upper()
    return gid if gid in STOREFRONT_GROUPS else None
