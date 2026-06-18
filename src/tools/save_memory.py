import glob
import os
import logging
import asyncio
import threading
from typing import Any

from src.paths import CONTEXT_DIR
from src.utils.async_utils import sleep

logger: logging.Logger = logging.getLogger(__name__)

_save_lock: threading.Lock = threading.Lock()

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": "Persists key user or system data to MEMORY.md so it can be recalled in future sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The category or key of the information (e.g. 'Name', 'Preference', 'Technology', 'Project')."
                },
                "value": {
                    "type": "string",
                    "description": "The value or detail to save. If passed empty, this key is removed from memory."
                }
            },
            "required": ["key", "value"]
        }
    }
}

_HEADER_TEMPLATE: list[str] = [
    "# MEMORY.md\n",
    "\n",
    "User: \n",
    "System: \n",
    "\n",
]


def _ensure_header(header_lines: list[str]) -> list[str]:
    has_title = any(line.strip().startswith("# MEMORY.md") for line in header_lines)
    has_user = any(line.strip().startswith("User:") for line in header_lines)
    has_system = any(line.strip().startswith("System:") for line in header_lines)

    if has_title and has_user and has_system:
        return header_lines

    logger.warning("MEMORY.md corrupt or missing header — repairing structure")
    out = list(_HEADER_TEMPLATE)
    for line in header_lines:
        s = line.strip()
        if s and not s.startswith("# MEMORY.md") and not s.startswith("User:") and not s.startswith("System:"):
            out.append(line)
    return out


def _apply_memory_operation(key: str, value: str, memories: dict[str, str]) -> str:
    key_clean = key.strip()
    value_clean = value.strip()

    if not key_clean:
        return "[ERROR] The key cannot be empty."

    if value_clean:
        memories[key_clean] = value_clean
        action_msg = f"saved key '{key_clean}' with value '{value_clean}'"
    else:
        if key_clean in memories:
            del memories[key_clean]
            action_msg = f"deleted key '{key_clean}'"
        else:
            action_msg = f"key '{key_clean}' did not exist in memory"
    return action_msg


def _write_memory_file(filepath: str, header_lines: list[str], memories: dict[str, str]) -> str | None:
    new_lines = list(header_lines)

    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()

    regular = {k: v for k, v in sorted(memories.items()) if not k.startswith("_archived:")}
    archived = {k: v for k, v in sorted(memories.items()) if k.startswith("_archived:")}

    new_lines.append("\n")
    new_lines.append("## Memories\n")
    for k, v in regular.items():
        new_lines.append(f"- **{k}**: {v}\n")

    if archived:
        new_lines.append("\n")
        new_lines.append("## Archived Memories\n")
        for k, v in archived.items():
            new_lines.append(f"- **{k}**: {v}\n")

    try:
        tmppath = filepath + ".tmp"
        with open(tmppath, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        os.replace(tmppath, filepath)
    except Exception:
        logger.exception("Failed to write to MEMORY.md")
        return "[ERROR] Could not write to MEMORY.md."
    return None
def _sync_read_and_write(filepath: str, key: str, value: str) -> tuple[str | None, str, list[str] | None]:
    """Sync function: lee MEMORY.md, aplica operación, escribe. Corre en to_thread."""
    header_lines = []
    memories = {}
    backup_lines: list[str] | None = None

    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            backup_lines = list(lines)
        except Exception:
            return "[ERROR] Could not read MEMORY.md.", "", None
    else:
        lines = list(_HEADER_TEMPLATE)

    in_memories_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- **") and "**:" in stripped:
            idx = stripped.find("**:")
            k = stripped[4:idx].strip()
            v = stripped[idx + 3 :].strip()
            memories[k] = v
        elif stripped.startswith("## Memories") or stripped.startswith("## Memoria") or stripped.startswith("## Archived Memories"):
            in_memories_section = True
        elif not in_memories_section:
            header_lines.append(line)

    header_lines = _ensure_header(header_lines)

    # Check for Syncthing conflict files and merge any new entries
    conflict_files = glob.glob(os.path.join(os.path.dirname(filepath), "MEMORY.md.sync-conflict-*"))
    if conflict_files:
        for conflict_path in conflict_files:
            try:
                with open(conflict_path, "r", encoding="utf-8") as f:
                    conflict_lines = f.readlines()
                for line in conflict_lines:
                    stripped = line.strip()
                    if stripped.startswith("- **") and "**: " in stripped:
                        idx = stripped.find("**:")
                        k = stripped[4:idx].strip()
                        v = stripped[idx + 3:].strip()
                        if k not in memories:
                            memories[k] = v + " [synced from conflict]"
                os.rename(conflict_path, conflict_path + ".resolved")
                logger.info("Merged %d entries from Syncthing conflict: %s",
                           len(conflict_lines), conflict_path)
            except Exception as e:
                logger.warning("Failed to process conflict file %s: %s", conflict_path, e)

    action_msg = _apply_memory_operation(key, value, memories)
    if action_msg.startswith("[ERROR]"):
        return action_msg, "", None

    err = _write_memory_file(filepath, header_lines, memories)
    return err, action_msg, backup_lines


async def run(**kwargs) -> str:
    key = kwargs.get("key") or kwargs.get("name", "")
    value = kwargs.get("value") or kwargs.get("content") or kwargs.get("text", "")
    _session_id = kwargs.get("_session_id")
    _invalidate_cache_fn = kwargs.get("_invalidate_cache_fn")
    _repos = kwargs.get("_repos")

    filepath = os.path.join(CONTEXT_DIR, "MEMORY.md")

    def _synced_op():
        with _save_lock:
            return _sync_read_and_write(filepath, key, value)

    err, action_msg, backup_lines = await run_in_thread(_synced_op)
    if err:
        logger.warning("MEMORY.md write failed (non-fatal): %s", err)
        action_msg = err

    # ── Async write to memory.db (global, synced) ─────────────────────
    db_ok = err is None
    if err is None and _repos is not None and _repos.memory is not None:
        key_clean = key.strip()
        value_clean = value.strip()
        if value_clean:
            ok = await _retry_upsert(_repos.memory.memory_index, key_clean, value_clean)
            if ok:
                logger.debug("save_memory also wrote to memory.db: %s", key_clean)
            else:
                db_ok = False
        elif key_clean:
            ok = await _retry_delete(_repos.memory.memory_index, key_clean)
            if ok:
                logger.debug("save_memory also deleted from memory.db: %s", key_clean)
            else:
                db_ok = False

    # ── Invalidate cache only after BOTH writes succeed ────────────────
    if db_ok and _invalidate_cache_fn is not None:
        _invalidate_cache_fn()

    # ── Restore MEMORY.md if file write succeeded but db write failed ─
    if not db_ok and backup_lines is not None:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(backup_lines)
            logger.info("Restored MEMORY.md from backup after db write failure")
        except Exception:
            logger.exception("Failed to restore MEMORY.md from backup")
    elif not db_ok and backup_lines is None and err is None:
        try:
            os.remove(filepath)
            logger.info("Removed MEMORY.md after db write failure (no backup)")
        except Exception:
            pass

    # ── Generate embedding for vector search ──────────────────────────
    store = _repos.memory.vector_store if _repos else None
    if value.strip() and store is not None:
        await _retry_embed(key, value, store)
    elif key.strip() and store is not None:
        await _retry_delete_embedding(key, store)

    return f"[OK] {action_msg} in MEMORY.md."


async def _retry_upsert(memory_index: Any, key: str, value: str, max_retries: int = 3) -> bool:
    """Try upsert to memory.db with backoff. Returns True on success."""
    for attempt in range(max_retries):
        try:
            await memory_index.upsert(key, value)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                await sleep(0.1 * (attempt + 1))
                continue
            logger.error("memory.db upsert failed after %d retries (key=%s, value_len=%d): %s", max_retries, key, len(value), e)
    return False


async def _retry_delete(memory_index: Any, key: str, max_retries: int = 3) -> bool:
    """Try get+delete from memory.db with backoff. Returns True on success."""
    for attempt in range(max_retries):
        try:
            old = await memory_index.get(key)
            if old is not None:
                await memory_index.delete(key)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                await sleep(0.1 * (attempt + 1))
                continue
            logger.error("memory.db delete failed after %d retries (key=%s): %s", max_retries, key, e)
    return False


async def _retry_embed(key: str, value: str, store: Any, max_retries: int = 3) -> None:
    """Try embedding + store with backoff."""
    for attempt in range(max_retries):
        try:
            await _embed_and_store(key, value, store)
            return
        except Exception as e:
            if attempt < max_retries - 1:
                await sleep(0.1 * (attempt + 1))
                continue
            logger.error("embedding store failed after %d retries (key=%s, value_len=%d): %s", max_retries, key, len(value), e)


async def _retry_delete_embedding(key: str, store: Any, max_retries: int = 3) -> None:
    """Try delete embedding with backoff."""
    for attempt in range(max_retries):
        try:
            deleted = store.delete_by_source(key)
            if deleted:
                logger.debug("Embedding deleted for key: %s", key)
            return
        except Exception as e:
            if attempt < max_retries - 1:
                await sleep(0.1 * (attempt + 1))
                continue
            logger.error("embedding delete failed after %d retries (key=%s): %s", max_retries, key, e)


async def _embed_and_store(key: str, value: str, store: Any) -> None:
    """Generate embedding for a memory entry and store it in sqlite-vec.

    Uses the injected VectorStore from DI instead of creating its own.
    """
    import hashlib
    from src.memory.embeddings.service import generate_embedding
    from src.memory.keywords.extractor import extract_keywords

    vec = await run_in_thread(generate_embedding, value)
    if all(v == 0.0 for v in vec):
        logger.warning(
            "Embedding for key '%s' is all zeros — model unavailable, "
            "semantic search degraded (keyword+entity only)",
            key,
        )

    text_hash = hashlib.md5(value.encode()).hexdigest()
    try:
        store.delete_by_source(key)
        rowid = store.insert(
            vec,
            source="memory",
            source_key=key,
            text=value[:2000],
            hash=text_hash,
        )
    except Exception as e:
        raise RuntimeError(f"vector_store insert failed: {e}") from e

    # Store keywords for hybrid retrieval
    if rowid:
        try:
            kws = extract_keywords(value, top_k=5)
            conn = store._get_conn()
            for word, score in kws:
                conn.execute(
                    "INSERT OR IGNORE INTO vec_keywords (rowid, word, score) VALUES (?, ?, ?)",
                    (rowid, word, round(score, 3))
                )
            conn.commit()
        except Exception:
            pass  # Non-fatal
    logger.debug("Embedding stored for key: %s (dim=%d)", key, len(vec))


async def _delete_embedding(key: str, store: Any) -> None:
    """Remove embedding for a deleted memory key."""
    deleted = store.delete_by_source(key)
    if deleted:
        logger.debug("Embedding deleted for key: %s", key)
