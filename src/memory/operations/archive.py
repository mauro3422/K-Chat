from __future__ import annotations

import logging
from typing import Any

from src.memory.operations._helpers import (
    _get_memory_md_path,
    _match_key_pattern,
    _parse_memory_md,
)

logger = logging.getLogger(__name__)


async def _archive(key_pattern: str = "", dry_run: bool = False, confirm: bool = False, repos: Any = None) -> str:
    """Archive matching entries by renaming their key to _archived:<original>."""
    if not key_pattern:
        return "[ERROR] archive requires key_pattern."

    md_path = _get_memory_md_path()
    memories = _parse_memory_md(md_path)

    matching = {k: v for k, v in memories.items()
                if _match_key_pattern(k, key_pattern) and not k.startswith("_archived:")}

    if not matching:
        return f"No entries match pattern '{key_pattern}'."

    if dry_run:
        lines = [f"Would archive {len(matching)} entries matching '{key_pattern}':"]
        for k in sorted(matching):
            lines.append(f"  {k} → _archived:{k}")
        return "\n".join(lines)

    if not confirm:
        return "[!] Use confirm=True to proceed."

    from src.tools.save_memory import run as save_run

    count = 0
    for k, v in matching.items():
        new_k = f"_archived:{k}"
        await save_run(key=k, value="", _repos=repos)
        await save_run(key=new_k, value=v, _repos=repos)
        count += 1

    return f"Archived {count} entries. Renamed to _archived:<original_key>."
