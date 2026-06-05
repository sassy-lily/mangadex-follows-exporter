#!/usr/bin/env python3
"""Convenience entry point so the tool can run as ``python export.py``.

Equivalent to ``python -m exporter``. Adds ``src/`` to the path so it also
works without an editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from exporter.cli import main

if __name__ == "__main__":
    main()
