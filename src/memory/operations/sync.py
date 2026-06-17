from __future__ import annotations

import json
import logging
from typing import Any

from src.memory.operations._helpers import (
    _get_memory_md_path,
    _match_key_pattern,
    _parse_memory_md,
)

logger = logging.getLogger(__name__)


async def _compare(key_pattern: str = "", fmt: str = "text", repos: Any = None) -> str:
    """Compare MEMORY.md vs memory.db entries."""
    md_path = _get_memory_md_path()
    md_memories = _parse_memory_md(md_path)

    mem = repos.memory if repos else None
    if mem is None:
        return "[ERROR] Memory system not available."
    db_entries = await mem.memory_index.get_all()

    db_keys = {e["key"] for e in db_entries}
    md_keys = set(md_memories.keys())

    only_md = sorted(k for k in (md_keys - db_keys) if _match_key_pattern(k, key_pattern))
    only_db = sorted(k for k in (db_keys - md_keys) if _match_key_pattern(k, key_pattern))

    common_diff = []
    for k in sorted(md_keys & db_keys):
        if not _match_key_pattern(k, key_pattern):
            continue
        mdv = md_memories[k]
        dbv = next(e["value"] for e in db_entries if e["key"] == k)
        if mdv != dbv:
            common_diff.append((k, mdv[:80], dbv[:80]))

    common_ok = sum(
        1 for k in sorted(md_keys & db_keys)
        if _match_key_pattern(k, key_pattern)
        and md_memories[k] == next(e["value"] for e in db_entries if e["key"] == k)
    )

    if fmt == "json":
        return json.dumps({
            "only_in_md": only_md, "only_in_db": only_db,
            "mismatched": [{"key": k, "md": mdv, "db": dbv} for k, mdv, dbv in common_diff],
            "matched": common_ok
        }, indent=2, ensure_ascii=False)

    lines = ["📋 **COMPARE: MEMORY.md vs memory.db**", ""]
    if key_pattern:
        lines.append(f"  (filter: {key_pattern})")
        lines.append("")
    if only_md:
        lines.append(f"🔴 Solo en MEMORY.md ({len(only_md)}):")
        lines.extend(f"   * {k}" for k in only_md)
        lines.append("")
    if only_db:
        lines.append(f"🟡 Solo en memory.db ({len(only_db)}):")
        lines.extend(f"   * {k}" for k in only_db)
        lines.append("")
    if common_diff:
        lines.append(f"🟠 Mismatched values ({len(common_diff)}):")
        lines.extend(f"   * {k}\n     MD: {mdv}...\n     DB: {dbv}..." for k, mdv, dbv in common_diff)
        lines.append("")
    lines.append(f"✅ Coinciden: {common_ok}")
    lines.append(f"📊 MD: {len(md_memories)} | DB: {len(db_entries)}")
    return "\n".join(lines)


async def _repair(dry_run: bool = False, confirm: bool = False, repos: Any = None) -> str:
    """Repair inconsistencies: delete orphans, fix keys."""
    if dry_run:
        pass
    elif not confirm:
        return "[!] Usa confirm=True para repair. Usa dry_run=True para previsualizar."

    md_path = _get_memory_md_path()
    md_memories = _parse_memory_md(md_path)

    mem = repos.memory if repos else None
    if mem is None:
        return "[ERROR] Memory system not available."
    db_entries = await mem.memory_index.get_all()

    db_keys = {e["key"] for e in db_entries}
    md_keys = set(md_memories.keys())

    orphans = sorted(db_keys - md_keys)
    only_md = sorted(md_keys - db_keys)

    renames = []
    for o in list(orphans):
        close = [k for k in only_md if o.split(":")[0] == k.split(":")[0]]
        if close:
            renames.append((o, close[0]))
            orphans.remove(o)
            only_md.remove(close[0])

    if dry_run:
        lines = ["🔧 **REPAIR PREVIEW**"]
        if orphans:
            lines.append(f"  Delete orphan: {', '.join(orphans)}")
        if renames:
            for old, new in renames:
                lines.append(f"  Rename '{old}' -> '{new}'")
        if not orphans and not renames:
            lines.append("  Nothing to repair.")
        return "\n".join(lines)

    count = 0
    for k in orphans:
        await mem.memory_index.delete(k)
        count += 1
    for old, new in renames:
        entry = next((e for e in db_entries if e["key"] == old), None)
        if entry:
            await mem.memory_index.delete(old)
            await mem.memory_index.upsert(new, entry["value"])
            count += 1

    return f"Reparadas {count} entradas ({len(orphans)} borradas, {len(renames)} renombradas)."


async def _reconstruct_from_memory_md(repos, dry_run=False) -> str:
    md_path = _get_memory_md_path()
    md_memories = _parse_memory_md(md_path)

    if not md_memories:
        return "[WARN] No entries found in MEMORY.md"

    if dry_run:
        return f"[DRY RUN] Reconstruct: would sync {len(md_memories)} entries to memory.db"

    idx = repos.memory.memory_index
    count = 0
    errors = 0
    for key, value in md_memories.items():
        try:
            await idx.upsert(key, value)
            count += 1
        except Exception as e:
            logger.warning("Error upserting %s: %s", key, e)
            errors += 1

    return f"[OK] Reconstructed: {count}/{len(md_memories)} entries synced to memory.db ({errors} errors)"


async def _sync(dry_run: bool = False, confirm: bool = False, repos: Any = None) -> str:
    if not repos or not repos.memory:
        return "[ERROR] memory.db no disponible."

    if not confirm:
        return await _reconstruct_from_memory_md(repos=repos, dry_run=dry_run)

    md_path = _get_memory_md_path()
    md_memories = _parse_memory_md(md_path)
    db_entries = await repos.memory.memory_index.get_all()

    db_keys = {e["key"] for e in db_entries}
    md_keys = set(md_memories.keys())

    to_add = md_keys - db_keys
    to_update = set()
    for k in md_keys & db_keys:
        if md_memories[k] != next(e["value"] for e in db_entries if e["key"] == k):
            to_update.add(k)
    to_delete = db_keys - md_keys

    if dry_run:
        return (
            f"🔄 **SYNC PREVIEW**\n"
            f"  Add: {len(to_add)}\n"
            f"  Update: {len(to_update)}\n"
            f"  Delete: {len(to_delete)}\n\n"
            f"Usa dry_run=False + confirm=True for destructive sync."
        )

    idx = repos.memory.memory_index
    for k in to_add:
        await idx.upsert(k, md_memories[k])
    for k in to_update:
        await idx.upsert(k, md_memories[k])
    for k in to_delete:
        await idx.delete(k)

    return f"Sync completa: {len(to_add)} agregadas, {len(to_update)} actualizadas, {len(to_delete)} eliminadas."
