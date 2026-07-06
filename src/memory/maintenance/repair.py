"""Safe repair/backfill helper for Kairos memory catalog state.

Default mode is read-only. ``--apply`` only writes inferred
memory_work_catalog rows; it never deletes vectors or edits sessions.
``--vectorize-missing`` is an explicit opt-in for generating missing vectors.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.maintenance.audit import content_hash_for_audit, group_into_exchanges, table_exists
from src.memory.embedding_identity import memory_entry_embedding_identity, session_exchange_embedding_identity
from src.memory.noise_filter import is_noise
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository


@dataclass
class RepairAction:
    action: str
    source: str
    source_key: str
    item_idx: int
    content_hash: str
    status: str = ""
    vec_rowid: int | None = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "source": self.source,
            "source_key": self.source_key,
            "item_idx": self.item_idx,
            "content_hash": self.content_hash,
            "status": self.status,
            "vec_rowid": self.vec_rowid,
            "reason": self.reason,
        }


@dataclass
class RepairReport:
    actions: list[RepairAction] = field(default_factory=list)
    applied_catalog_rows: int = 0
    vectorized_sessions: dict[str, int] = field(default_factory=dict)
    pruned_stale_vectors: int = 0

    @property
    def counts(self) -> dict[str, int]:
        data: dict[str, int] = {}
        for action in self.actions:
            data[action.action] = data.get(action.action, 0) + 1
        return data

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "applied_catalog_rows": self.applied_catalog_rows,
            "vectorized_sessions": self.vectorized_sessions,
            "pruned_stale_vectors": self.pruned_stale_vectors,
            "actions": [action.as_dict() for action in self.actions],
        }


def _dedupe_actions(actions: list[RepairAction]) -> list[RepairAction]:
    """Collapse repeated logical repair actions from legacy catalog identities."""

    seen: set[tuple[Any, ...]] = set()
    deduped: list[RepairAction] = []
    for action in actions:
        key = (
            action.action,
            action.source,
            action.source_key,
            action.item_idx,
            action.content_hash,
            action.status,
            action.vec_rowid,
            action.reason,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


@contextmanager
def _connect(path: str, *, readonly: bool) -> Iterator[sqlite3.Connection]:
    if readonly:
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _vec_rows_by_session_idx(conn: sqlite3.Connection, session_id: str, idx: int) -> list[sqlite3.Row]:
    if not table_exists(conn, "vec_meta"):
        return []
    return conn.execute(
        """
        SELECT rowid, content_hash, hash
        FROM vec_meta
        WHERE source='session' AND source_key=? AND exchange_idx=?
        ORDER BY rowid DESC
        """,
        (session_id, idx),
    ).fetchall()


def _find_vec_by_hash(conn: sqlite3.Connection, content_hash: str) -> sqlite3.Row | None:
    if not table_exists(conn, "vec_meta"):
        return None
    return conn.execute(
        """
        SELECT rowid, source, source_key, exchange_idx
        FROM vec_meta
        WHERE content_hash=? OR hash=?
        ORDER BY source='session' DESC, rowid DESC
        LIMIT 1
        """,
        (content_hash, content_hash),
    ).fetchone()


def _vec_row_exists(conn: sqlite3.Connection, rowid: int) -> bool:
    if not table_exists(conn, "vec_meta"):
        return False
    row = conn.execute("SELECT 1 FROM vec_meta WHERE rowid = ?", (rowid,)).fetchone()
    return row is not None


def _catalog_row(conn: sqlite3.Connection, session_id: str, idx: int) -> sqlite3.Row | None:
    return _catalog_row_for(conn, source="session", source_key=session_id, item_idx=idx)


def _catalog_identity_kwargs(source: str) -> dict[str, str]:
    if source == "session":
        return session_exchange_embedding_identity().as_catalog_kwargs()
    if source == "memory":
        return memory_entry_embedding_identity().as_catalog_kwargs()
    return {}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _catalog_row_for(conn: sqlite3.Connection, *, source: str, source_key: str, item_idx: int) -> sqlite3.Row | None:
    if not table_exists(conn, "memory_work_catalog"):
        return None
    identity = _catalog_identity_kwargs(source)
    identity_columns = ("pipeline", "pipeline_version", "model_id", "model_version")
    if identity and set(identity_columns).issubset(_table_columns(conn, "memory_work_catalog")):
        return conn.execute(
            """
            SELECT content_hash, status, vec_rowid
            FROM memory_work_catalog
            WHERE source=? AND source_key=? AND item_idx=?
              AND pipeline=? AND pipeline_version=?
              AND model_id=? AND model_version=?
            """,
            (
                source,
                source_key,
                item_idx,
                identity["pipeline"],
                identity["pipeline_version"],
                identity["model_id"],
                identity["model_version"],
            ),
        ).fetchone()
    return conn.execute(
        """
        SELECT content_hash, status, vec_rowid
        FROM memory_work_catalog
        WHERE source=? AND source_key=? AND item_idx=?
        """,
        (source, source_key, item_idx),
    ).fetchone()


def _content_hash_from_vec(row: sqlite3.Row) -> str:
    return str(row["content_hash"] or row["hash"] or "")


def _plan_memory_vector_catalog_repairs(memory_conn: sqlite3.Connection, report: RepairReport) -> None:
    if not table_exists(memory_conn, "vec_meta"):
        return

    rows = memory_conn.execute(
        """
        SELECT rowid, source_key, exchange_idx, hash, content_hash
        FROM vec_meta
        WHERE source='memory'
        ORDER BY rowid ASC
        """
    ).fetchall()
    for row in rows:
        source_key = str(row["source_key"] or "")
        item_idx = int(row["exchange_idx"] or 0)
        digest = _content_hash_from_vec(row)
        if not source_key or not digest:
            continue
        catalog = _catalog_row_for(memory_conn, source="memory", source_key=source_key, item_idx=item_idx)
        if catalog and str(catalog["content_hash"]) == digest and str(catalog["status"]) in {
            "embedded",
            "deduped",
            "noise",
        }:
            vec_rowid = catalog["vec_rowid"]
            if vec_rowid is None or _vec_row_exists(memory_conn, int(vec_rowid)):
                continue
            report.actions.append(RepairAction(
                action="broken_catalog_link",
                source="memory",
                source_key=source_key,
                item_idx=item_idx,
                content_hash=digest,
                status=str(catalog["status"]),
                vec_rowid=int(vec_rowid),
                reason="catalog_vec_row_missing",
            ))
        report.actions.append(RepairAction(
            action="catalog_memory_embedded",
            source="memory",
            source_key=source_key,
            item_idx=item_idx,
            content_hash=digest,
            status="embedded",
            vec_rowid=int(row["rowid"]),
            reason="existing_memory_vector",
        ))


def _plan_orphan_memory_catalog_repairs(memory_conn: sqlite3.Connection, report: RepairReport) -> None:
    if not table_exists(memory_conn, "memory_work_catalog") or not table_exists(memory_conn, "memory_index"):
        return

    has_vec_meta = table_exists(memory_conn, "vec_meta")
    join_vec = "LEFT JOIN vec_meta v ON v.rowid = c.vec_rowid" if has_vec_meta else ""
    vec_missing_clause = "AND (c.vec_rowid IS NULL OR v.rowid IS NULL)" if has_vec_meta else ""
    rows = memory_conn.execute(
        f"""
        SELECT c.source, c.source_key, c.item_idx, c.content_hash, c.status, c.vec_rowid
        FROM memory_work_catalog c
        {join_vec}
        LEFT JOIN memory_index m ON m.key = c.source_key
        WHERE c.source = 'memory'
          AND c.status IN ('embedded', 'deduped')
          {vec_missing_clause}
          AND m.key IS NULL
        ORDER BY c.source_key, c.item_idx
        """
    ).fetchall()
    for row in rows:
        report.actions.append(RepairAction(
            action="orphan_catalog_row",
            source=str(row["source"]),
            source_key=str(row["source_key"]),
            item_idx=int(row["item_idx"]),
            content_hash=str(row["content_hash"] or ""),
            status=str(row["status"] or ""),
            vec_rowid=int(row["vec_rowid"]) if row["vec_rowid"] is not None else None,
            reason="memory_key_and_vec_missing",
        ))


def _plan_orphan_session_catalog_repairs(
    sessions_conn: sqlite3.Connection,
    memory_conn: sqlite3.Connection,
    report: RepairReport,
) -> None:
    if not table_exists(memory_conn, "memory_work_catalog") or not table_exists(sessions_conn, "sessions"):
        return

    rows = memory_conn.execute(
        """
        SELECT c.source, c.source_key, c.item_idx, c.content_hash, c.status, c.vec_rowid
        FROM memory_work_catalog c
        LEFT JOIN vec_meta v ON v.rowid = c.vec_rowid
        WHERE c.source = 'session'
          AND c.status IN ('embedded', 'deduped')
          AND c.vec_rowid IS NOT NULL
          AND v.rowid IS NULL
        ORDER BY c.source_key, c.item_idx
        """
    ).fetchall()
    for row in rows:
        session = sessions_conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?",
            (str(row["source_key"]),),
        ).fetchone()
        if session is not None:
            continue
        report.actions.append(RepairAction(
            action="orphan_catalog_row",
            source=str(row["source"]),
            source_key=str(row["source_key"]),
            item_idx=int(row["item_idx"]),
            content_hash=str(row["content_hash"] or ""),
            status=str(row["status"] or ""),
            vec_rowid=int(row["vec_rowid"]) if row["vec_rowid"] is not None else None,
            reason="session_and_vec_missing",
        ))


def plan_repairs(*, sessions_db: str, memory_db: str) -> RepairReport:
    report = RepairReport()
    with _connect(sessions_db, readonly=True) as sessions_conn, _connect(memory_db, readonly=True) as memory_conn:
        if not table_exists(sessions_conn, "sessions") or not table_exists(sessions_conn, "messages"):
            return report
        sessions = sessions_conn.execute(
            "SELECT session_id, name FROM sessions ORDER BY created_at ASC"
        ).fetchall()

        for session in sessions:
            session_id = str(session["session_id"])
            messages = sessions_conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            exchanges = group_into_exchanges(messages)
            for exchange in exchanges:
                idx = int(exchange["idx"])
                text = str(exchange["text"])
                digest = content_hash_for_audit(text)

                same_idx_rows = _vec_rows_by_session_idx(memory_conn, session_id, idx)
                for row in same_idx_rows:
                    old_hash = str(row["content_hash"] or row["hash"] or "")
                    if old_hash and old_hash != digest:
                        report.actions.append(RepairAction(
                            action="stale_vector",
                            source="session",
                            source_key=session_id,
                            item_idx=idx,
                            content_hash=old_hash,
                            vec_rowid=int(row["rowid"]),
                            reason=f"current_hash={digest[:12]}",
                        ))

                catalog = _catalog_row(memory_conn, session_id, idx)
                if catalog and str(catalog["content_hash"]) == digest and str(catalog["status"]) in {
                    "embedded",
                    "deduped",
                    "noise",
                }:
                    vec_rowid = catalog["vec_rowid"]
                    if vec_rowid is None or str(catalog["status"]) == "noise" or _vec_row_exists(memory_conn, int(vec_rowid)):
                        continue
                    report.actions.append(RepairAction(
                        action="broken_catalog_link",
                        source="session",
                        source_key=session_id,
                        item_idx=idx,
                        content_hash=digest,
                        status=str(catalog["status"]),
                        vec_rowid=int(vec_rowid),
                        reason="catalog_vec_row_missing",
                    ))

                if len(text) < 30:
                    report.actions.append(RepairAction(
                        action="catalog_noise",
                        source="session",
                        source_key=session_id,
                        item_idx=idx,
                        content_hash=digest,
                        status="noise",
                        reason="short_text",
                    ))
                    continue

                noise, reason = is_noise(text)
                if noise:
                    report.actions.append(RepairAction(
                        action="catalog_noise",
                        source="session",
                        source_key=session_id,
                        item_idx=idx,
                        content_hash=digest,
                        status="noise",
                        reason=reason,
                    ))
                    continue

                exact_same_idx = next(
                    (
                        row for row in same_idx_rows
                        if str(row["content_hash"] or row["hash"] or "") == digest
                    ),
                    None,
                )
                if exact_same_idx is not None:
                    report.actions.append(RepairAction(
                        action="catalog_embedded",
                        source="session",
                        source_key=session_id,
                        item_idx=idx,
                        content_hash=digest,
                        status="embedded",
                        vec_rowid=int(exact_same_idx["rowid"]),
                        reason="existing_session_vector",
                    ))
                    continue

                existing = _find_vec_by_hash(memory_conn, digest)
                if existing is not None:
                    report.actions.append(RepairAction(
                        action="catalog_deduped",
                        source="session",
                        source_key=session_id,
                        item_idx=idx,
                        content_hash=digest,
                        status="deduped",
                        vec_rowid=int(existing["rowid"]),
                        reason="existing_content_hash",
                    ))
                else:
                    report.actions.append(RepairAction(
                        action="missing_vector",
                        source="session",
                        source_key=session_id,
                        item_idx=idx,
                        content_hash=digest,
                        reason="no_matching_vector",
                    ))
        _plan_memory_vector_catalog_repairs(memory_conn, report)
        _plan_orphan_memory_catalog_repairs(memory_conn, report)
        _plan_orphan_session_catalog_repairs(sessions_conn, memory_conn, report)
    report.actions = _dedupe_actions(report.actions)
    return report


def apply_catalog_repairs(*, memory_db: str, report: RepairReport) -> int:
    catalog = MemoryWorkCatalogRepository(memory_db)
    applied = 0
    for action in report.actions:
        if action.action not in {"catalog_embedded", "catalog_deduped", "catalog_noise", "catalog_memory_embedded"}:
            continue
        catalog.mark(
            source=action.source,
            source_key=action.source_key,
            item_idx=action.item_idx,
            content_hash=action.content_hash,
            status=action.status,
            vec_rowid=action.vec_rowid,
            reason=action.reason,
            metadata={"repair_action": action.action},
            **_catalog_identity_kwargs(action.source),
        )
        applied += 1
    orphan_rows = [action for action in report.actions if action.action == "orphan_catalog_row"]
    if orphan_rows:
        with _connect(memory_db, readonly=False) as conn:
            for action in orphan_rows:
                conn.execute(
                    """
                    DELETE FROM memory_work_catalog
                    WHERE source = ? AND source_key = ? AND item_idx = ?
                    """,
                    (action.source, action.source_key, action.item_idx),
                )
                applied += 1
            conn.commit()
    return applied


def _delete_if_table_exists(conn: sqlite3.Connection, table: str, column: str, rowid: int) -> None:
    if table_exists(conn, table):
        conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (rowid,))


def prune_stale_vectors(*, memory_db: str, report: RepairReport) -> int:
    rowids = sorted({
        int(action.vec_rowid)
        for action in report.actions
        if action.action == "stale_vector" and action.vec_rowid is not None
    })
    if not rowids:
        return 0

    conn = sqlite3.connect(memory_db)
    try:
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(conn)
        except Exception:
            pass
        for rowid in rowids:
            _delete_if_table_exists(conn, "vec_keywords", "rowid", rowid)
            _delete_if_table_exists(conn, "exchange_clusters", "exchange_rowid", rowid)
            _delete_if_table_exists(conn, "entity_mentions", "exchange_rowid", rowid)
            _delete_if_table_exists(conn, "vec_entries", "rowid", rowid)
            _delete_if_table_exists(conn, "vec_meta", "rowid", rowid)
        conn.commit()
        return len(rowids)
    finally:
        conn.close()


async def vectorize_missing(report: RepairReport) -> dict[str, int]:
    from src.memory.repos import get_repos
    from src.memory.vectorize_sessions import vectorize_session

    targets: dict[str, set[int]] = {}
    for action in report.actions:
        if action.action == "missing_vector":
            targets.setdefault(action.source_key, set()).add(action.item_idx)

    results: dict[str, int] = {}
    repos = get_repos()
    for session_id, indexes in sorted(targets.items()):
        count, _noise_count, _mappings, _entities = await vectorize_session(
            session_id,
            repos=repos,
            exchange_indexes=indexes,
        )
        results[session_id] = count
    return results


# CLI moved to repair_cli.py
