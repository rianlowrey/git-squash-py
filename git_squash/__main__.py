#!/usr/bin/env python3
"""Main entry point for git-squash when run as python -m git_squash."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())