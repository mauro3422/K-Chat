"""CLI compatibility wrapper for memory repair maintenance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._python_bootstrap import ensure_repo_python
from src.memory.maintenance.repair import *  # noqa: F401,F403
from src.memory.maintenance.repair_cli import main


if __name__ == "__main__":
    ensure_repo_python(__file__, command_name="scripts/memory_repair.py")
    raise SystemExit(main())
