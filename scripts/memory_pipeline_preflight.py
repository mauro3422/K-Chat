"""CLI compatibility wrapper for memory pipeline preflight."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.maintenance.pipeline_preflight import *  # noqa: F401,F403
from src.memory.maintenance.pipeline_preflight import main


if __name__ == "__main__":
    raise SystemExit(main())
