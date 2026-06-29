"""CLI compatibility wrapper for memory audit maintenance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.maintenance.audit import *  # noqa: F401,F403
from src.memory.maintenance.audit import _content_hash, _group_into_exchanges, _table_exists, main


if __name__ == "__main__":
    raise SystemExit(main())
