"""Module entry point: ``python -m apps.worker``."""

from __future__ import annotations

import sys

from apps.worker.cli import main

if __name__ == "__main__":
    sys.exit(main())
