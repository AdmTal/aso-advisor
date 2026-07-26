"""Entry point for `python -m aso_advisor`."""

import sys

from .cli import main

if __name__ == '__main__':
    sys.exit(main())
