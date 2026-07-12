"""Build an auditable, human-readable queue from conceptual candidates."""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.curator.conceptual_candidates import audit_candidates, discover_conceptual_candidates, write_candidate_dataset
from src.memory.curator.vigency import audit_bug_candidates


def build_queue(root: str | Path) -> Path:
    base = Path(root)
    candidates = discover_conceptual_candidates(base)
    canonical_path = base / "MEMORY.md"
    canonical = canonical_path.read_text(encoding="utf-8", errors="replace") if canonical_path.exists() else ""
    documentation_paths = (
        base / "bugs.md",
        base / "ROADMAP.md",
        base / "HANDOVER_AGENTE_MEMORIA.md",
    )
    docs = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in documentation_paths
        if path.exists()
    )
    queue = audit_bug_candidates(audit_candidates(candidates, canonical), project_text="", documentation_text=docs)
    path = base / "memory" / "curator-review-queue.jsonl"
    return write_candidate_dataset(path, queue)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the curator review queue from conceptual candidates.")
    parser.add_argument("--root", default=str(ROOT), help="Project root containing memory/ and MEMORY.md.")
    args = parser.parse_args(argv)
    print(build_queue(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
