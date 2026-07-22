#!/usr/bin/env python3
"""
Auto Cost Engine — AI Provider Connectivity Verification (Standalone CLI)

Usage
-----
    python scripts/verify_ai_connectivity.py          # concise output
    python scripts/verify_ai_connectivity.py --verbose # full endpoint dumps
    python scripts/verify_ai_connectivity.py --output /custom/path.json

Environment variables read
--------------------------
    MIMO_API_KEY, MIMO_API_BASE,
    DEEPSEEK_API_KEY, DEEPSEEK_API_BASE

    Also loads from **.env** when present in the project root.

Exit codes
----------
    0   Both MiMo and DeepSeek are reachable.
    1   One or both providers are unreachable.
"""

from __future__ import annotations

import sys

# Ensure the backend root is on sys.path so the test module can find
# its relative imports if needed.
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from scripts.connectivity_test import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
