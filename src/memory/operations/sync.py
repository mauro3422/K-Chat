from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from typing import Any

from src.memory.operations._helpers import (
    _get_memory_md_path,
    _match_key_pattern,
    _parse_memory_md,
)

logger = logging.getLogger(__name__)


async def _load_memory_state_async(repos: Any = None) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    md_memories = _parse_memory_md(_get_memory_md_path())
    db_entries: dict[str, dict[str, Any]] = {}

    mem = repos.memory if repos else None
    if mem is None:
        return md_memories, db_entries

    for entry in await mem.memory_index.get_all():
        key = str(entry.get("key", ""))
        if not key:
            continue
        db_entries[key] = {
            "value": str(entry.get("value", "")),
            "updated_at": str(entry.get("updated_at", "")),
        }
    return md_memories, db_entries


def _build_memory_diff(
    md_memories: dict[str, str],
    db_entries: dict[str, dict[str, Any]],
    key_pattern: str = "",
) -> dict[str, Any]:
    md_keys = {k for k in md_memories if _match_key_pattern(k, key_pattern)}
    db_keys = {k for k in db_entries if _match_key_pattern(k, key_pattern)}

    only_md = sorted(md_keys - db_keys)
    only_db = sorted(db_keys - md_keys)
    mismatched = []
    matched = 0

    for key in sorted(md_keys & db_keys):
        md_value = md_memories[key]
        db_entry = db_entries[key]
        db_value = db_entry.get("value", "")
        if md_value == db_value:
            matched += 1
            continue
        mismatched.append(
            {
                "key": key,
                "md": md_value,
                "db": db_value,
                "db_updated_at": db_entry.get("updated_at", ""),
                "md_len": len(md_value),
                "db_len": len(db_value),
            }
        )

    return {
        "only_in_md": only_md,
        "only_in_db": only_db,
        "mismatched": mismatched,
        "matched": matched,
        "md_total": len(md_memories),
        "db_total": len(db_entries),
    }


def _key_similarity(left: str, right: str) -> float:
    left_norm = " ".join(left.lower().replace("_", " ").replace("-", " ").split())
    right_norm = " ".join(right.lower().replace("_", " ").replace("-", " ").split())
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _best_rename_candidates(
    orphan_keys: list[str],
    md_keys: list[str],
    *,
    threshold: float = 0.82,
    margin: float = 0.08,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for orphan in orphan_keys:
        scored = [
            {"key": md_key, "score": _key_similarity(orphan, md_key)}
            for md_key in md_keys
        ]
        scored = [item for item in scored if item["score"] >= threshold]
        scored.sort(key=lambda item: item["score"], reverse=True)
        if not scored:
            continue
        best = scored[0]
        second = scored[1]["score"] if len(scored) > 1 else 0.0
        candidates.append(
            {
                "orphan": orphan,
                "target": best["key"],
                "score": round(best["score"], 3),
                "ambiguous": len(scored) > 1 and (best["score"] - second) < margin,
            }
        )
    return candidates


async def _compare(key_pattern: str = "", fmt: str = "text", repos: Any = None) -> str:
    """Compare MEMORY.md vs memory.db entries."""
    md_memories, db_entries = await _load_memory_state_async(repos)
    if repos and getattr(repos, "memory", None) is None:
        return "[ERROR] Memory system not available."

    diff = _build_memory_diff(md_memories, db_entries, key_pattern=key_pattern)
    rename_candidates = _best_rename_candidates(diff["only_in_db"], diff["only_in_md"])

    if fmt == "json":
        return json.dumps(
            {
                "only_in_md": diff["only_in_md"],
                "only_in_db": diff["only_in_db"],
                "mismatched": diff["mismatched"],
                "rename_candidates": rename_candidates,
                "matched": diff["matched"],
                "md_total": diff["md_total"],
                "db_total": diff["db_total"],
            },
            indent=2,
            ensure_ascii=False,
        )

    lines = ["📋 **COMPARE: MEMORY.md vs memory.db**", ""]
    if key_pattern:
        lines.append(f"  (filter: {key_pattern})")
        lines.append("")
    if diff["only_in_md"]:
        lines.append(f"🔴 Solo en MEMORY.md ({len(diff['only_in_md'])}):")
        lines.extend(f"   * {k}" for k in diff["only_in_md"])
        lines.append("")
    if diff["only_in_db"]:
        lines.append(f"🟡 Solo en memory.db ({len(diff['only_in_db'])}):")
        lines.extend(f"   * {k}" for k in diff["only_in_db"])
        lines.append("")
    if diff["mismatched"]:
        lines.append(f"🟠 Mismatched values ({len(diff['mismatched'])}):")
        lines.extend(
            f"   * {item['key']}\n"
            f"     MD: {item['md'][:80]}...\n"
            f"     DB: {item['db'][:80]}..."
            for item in diff["mismatched"]
        )
        lines.append("")
    if rename_candidates:
        lines.append(f"🟣 Rename candidates ({len(rename_candidates)}):")
        lines.extend(
            f"   * {item['orphan']} -> {item['target']} (score={item['score']:.3f}"
            + (", ambiguous)" if item["ambiguous"] else ")")
            for item in rename_candidates
        )
        lines.append("")
    lines.append(f"✅ Coinciden: {diff['matched']}")
    lines.append(f"📊 MD: {diff['md_total']} | DB: {diff['db_total']}")
    return "\n".join(lines)


async def _repair(dry_run: bool = False, confirm: bool = False, repos: Any = None) -> str:
    """Repair inconsistencies: delete orphans, fix obvious key renames."""
    if dry_run is False and not confirm:
        return "[!] Usa confirm=True para repair. Usa dry_run=True para previsualizar."

    md_memories, db_entries = await _load_memory_state_async(repos)
    if repos and getattr(repos, "memory", None) is None:
        return "[ERROR] Memory system not available."

    diff = _build_memory_diff(md_memories, db_entries)
    orphans = list(diff["only_in_db"])
    only_md = list(diff["only_in_md"])
    rename_candidates = _best_rename_candidates(orphans, only_md)

    renames: list[tuple[str, str]] = []
    unresolved_orphans = list(orphans)
    unresolved_md = list(only_md)
    for candidate in rename_candidates:
        if candidate["ambiguous"]:
            continue
        old = candidate["orphan"]
        new = candidate["target"]
        if old in unresolved_orphans and new in unresolved_md:
            renames.append((old, new))
            unresolved_orphans.remove(old)
            unresolved_md.remove(new)
    orphans = unresolved_orphans
    only_md = unresolved_md

    if dry_run:
        lines = ["🔧 **REPAIR PREVIEW**"]
        if orphans:
            lines.append(f"  Delete orphan: {', '.join(orphans)}")
        if renames:
            for old, new in renames:
                lines.append(f"  Rename '{old}' -> '{new}'")
        ambiguous = [item for item in rename_candidates if item["ambiguous"]]
        if ambiguous:
            lines.append("  Conflicting rename candidates:")
            for item in ambiguous:
                lines.append(f"    - {item['orphan']} -> {item['target']} (score={item['score']:.3f})")
        if not orphans and not renames:
            lines.append("  Nothing to repair.")
        return "\n".join(lines)

    mem = repos.memory
    count = 0
    for key in orphans:
        await mem.memory_index.delete(key)
        count += 1
    for old, new in renames:
        entry_value = md_memories.get(new, db_entries.get(old, {}).get("value"))
        if entry_value is not None:
            await mem.memory_index.delete(old)
            await mem.memory_index.upsert(new, entry_value)
            count += 1

    unresolved = len(orphans)
    return f"Reparadas {count} entradas ({unresolved} borradas, {len(renames)} renombradas)."


async def _reconstruct_from_memory_md(repos: Any, dry_run: bool = False) -> str:
    md_memories, _ = await _load_memory_state_async(repos)
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

    md_memories, db_entries = await _load_memory_state_async(repos)
    diff = _build_memory_diff(md_memories, db_entries)

    if dry_run:
        return (
            f"🔄 **SYNC PREVIEW**\n"
            f"  Add: {len(diff['only_in_md'])}\n"
            f"  Update: {len(diff['mismatched'])}\n"
            f"  Delete: {len(diff['only_in_db'])}\n\n"
            f"Coinciden: {diff['matched']}\n"
            f"Usa dry_run=False + confirm=True para aplicar cambios."
        )

    idx = repos.memory.memory_index
    for key in diff["only_in_md"]:
        await idx.upsert(key, md_memories[key])
    for item in diff["mismatched"]:
        await idx.upsert(item["key"], md_memories[item["key"]])
    for key in diff["only_in_db"]:
        await idx.delete(key)

    return (
        f"Sync completa: {len(diff['only_in_md'])} agregadas, "
        f"{len(diff['mismatched'])} actualizadas, {len(diff['only_in_db'])} eliminadas. "
        f"Coinciden: {diff['matched']}"
    )
