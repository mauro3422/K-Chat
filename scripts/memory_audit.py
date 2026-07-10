"""CLI compatibility wrapper for memory audit maintenance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._python_bootstrap import ensure_repo_python
from src.memory.maintenance.audit import *  # noqa: F401,F403
from src.memory.maintenance.audit import (
    content_hash_for_audit as _content_hash,
    group_into_exchanges as _group_into_exchanges,
    table_exists as _table_exists,
)
from src.memory.maintenance.audit_cli import main


if __name__ == "__main__":
    ensure_repo_python(__file__, command_name="scripts/memory_audit.py")
    raise SystemExit(main())
