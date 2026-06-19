import glob
import logging
import os
import threading
from typing import Any

from src.memory.operations._helpers import _parse_memory_md, _write_memory_md
from src.paths import CONTEXT_DIR
from src.utils.async_utils import run_in_thread, sleep

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
                    "description": "The category or key of the information (e.g. 'Name', 'Preference', 'Technology', 'Project').",
                },
                "value": {
                    "type": "string",
                    "description": "The value or detail to save. If passed empty, this key is removed from memory.",
                },
            },
            "required": ["key", "value"],
        },
    }
}


def _apply_memory_operation(key: str, value: str, memories: dict[str, str]) -> str:
    key_clean = key.strip()
    value_clean = value.strip()

    if not key_clean:
        return "[ERROR] The key cannot be empty."

    if value_clean:
        memories[key_clean] = value_clean
        return f"saved key '{key_clean}' with value '{value_clean}'"

    if key_clean in memories:
        del memories[key_clean]
        return f"deleted key '{key_clean}'"

    return f"key '{key_clean}' did not exist in memory"


def _sync_read_and_write(filepath: str, key: str, value: str) -> tuple[str | None, str, list[str] | None]:
    """Sync function: reads MEMORY.md, applies the operation, writes it back."""
    memories: dict[str, str] = {}
    backup_lines: list[str] | None = None

    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                backup_lines = f.readlines()
            memories = _parse_memory_md(filepath)
        except Exception:
            return "[ERROR] Could not read MEMORY.md.", "", None

    conflict_files = glob.glob(os.path.join(os.path.dirname(filepath), "MEMORY.md.sync-conflict-*"))
    if conflict_files:
        for conflict_path in conflict_files:
            try:
                conflict_memories = _parse_memory_md(conflict_path)
                for k, v in conflict_memories.items():
                    if k not in memories:
                        memories[k] = v + " [synced from conflict]"
                os.rename(conflict_path, conflict_path + ".resolved")
                logger.info("Merged %d entries from Syncthing conflict: %s", len(conflict_memories), conflict_path)
            except Exception as e:
                logger.warning("Failed to process conflict file %s: %s", conflict_path, e)

    action_msg = _apply_memory_operation(key, value, memories)
    if action_msg.startswith("[ERROR]"):
        return action_msg, "", None

    try:
        _write_memory_md(filepath, memories)
    except Exception:
        logger.exception("Failed to write to MEMORY.md")
        return "[ERROR] Could not write to MEMORY.md.", action_msg, backup_lines
    return None, action_msg, backup_lines


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

    if db_ok and _invalidate_cache_fn is not None:
        _invalidate_cache_fn()

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
            logger.error(
                "memory.db upsert failed after %d retries (key=%s, value_len=%d): %s",
                max_retries,
                key,
                len(value),
                e,
            )
    return False


async def _retry_delete(memory_index: Any, key: str, max_retries: int = 3) -> bool:
    """Try get+delete from memory.db with backoff. Returns True on success."""
    for attempt in range(max_retries):
        try:
            existing = await memory_index.get(key)
            if existing is not None:
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
            logger.error(
                "embedding store failed after %d retries (key=%s, value_len=%d): %s",
                max_retries,
                key,
                len(value),
                e,
            )


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
    """Generate embedding for a memory entry and store it in sqlite-vec."""
    import hashlib

    from src.memory.embeddings.service import generate_embedding
    from src.memory.keywords.extractor import extract_keywords

    vec = await run_in_thread(generate_embedding, value)
    if all(v == 0.0 for v in vec):
        logger.warning(
            "Embedding for key '%s' is all zeros - model unavailable, semantic search degraded (keyword+entity only)",
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

    if rowid:
        try:
            kws = extract_keywords(value, top_k=5)
            conn = store._get_conn()
            for word, score in kws:
                conn.execute(
                    "INSERT OR IGNORE INTO vec_keywords (rowid, word, score) VALUES (?, ?, ?)",
                    (rowid, word, round(score, 3)),
                )
            conn.commit()
        except Exception:
            pass
    logger.debug("Embedding stored for key: %s (dim=%d)", key, len(vec))


async def _delete_embedding(key: str, store: Any) -> None:
    """Remove embedding for a deleted memory key."""
    deleted = store.delete_by_source(key)
    if deleted:
        logger.debug("Embedding deleted for key: %s", key)
