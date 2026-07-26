"""ASO Advisor — an App Store Optimization advisor for versioned metadata.

The package holds two layers.

The offline layer reads the YAML metadata of your workspace and returns
prioritized suggestions. It keeps the state of each suggestion in SQLite, so
each run tells you what is new, what is still open, and what your last push
resolved.

The live layer reads the public endpoints of Apple: real search positions, the
metadata of your competitors, the autocomplete of the store, and your recent
reviews. It needs no account and no key.

Documentation: https://github.com/AdmTal/aso-advisor/tree/main/docs
"""

__version__ = '1.0.0'
__all__ = ['__version__']
