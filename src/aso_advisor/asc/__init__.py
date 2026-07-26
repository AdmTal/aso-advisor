"""The App Store Connect layer: pull metadata, push metadata, push assets.

This is the only part of the tool that writes to App Store Connect. It needs
an API key that you make yourself. Read `docs/app-store-connect.md`, or run
`aso auth` for the short version.

Install the extra dependency with:

    pip install 'aso-advisor[sync]'
"""

from .client import ASCAuthError, ASCClient, ASCError, Credentials

__all__ = ['ASCAuthError', 'ASCClient', 'ASCError', 'Credentials']
