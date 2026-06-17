"""Schema and migrations for memory.db (curated, syncable memory).

Uses synchronous sqlite3 for initialization to avoid aiosqlite thread
issues when creating a new connection after closing a previous one.
"""

import logging
import os
import sqlite3

from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.migration_runner import run_pending_migrations
from src.memory.lifecycle import mark_initialized

logger = logging.getLogger(__name__)


def _migration_001_global_memory_index(conn: sqlite3.Connection, engine) -> None:
    """Create the global memory_index table.

    If the old session-scoped table exists (with session_id column),
    migrate its data and replace with the new global schema.
    """
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_index'")
    old_table = cursor.fetchone()

    if old_table:
        col_cursor = conn.execute("PRAGMA table_info(memory_index)")
        columns = col_cursor.fetchall()
        has_session_id = any(c[1] == "session_id" for c in columns)  # column name at index 1

        if has_session_id:
            logger.info("Migrating old session-scoped memory_index to new global schema")
            try:
                rows = conn.execute(
                    "SELECT key, value, updated_at FROM memory_index ORDER BY updated_at DESC"
                ).fetchall()
            except Exception:
                rows = []

            conn.execute("DROP TABLE memory_index")

            conn.execute("""
                CREATE TABLE memory_index (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            seen = set()
            for row in rows:
                key = row[0]
                if key not in seen:
                    seen.add(key)
                    try:
                        conn.execute(
                            "INSERT INTO memory_index (key, value, updated_at) VALUES (?, ?, ?)",
                            (key, row[1], row[2] if len(row) > 2 else None),
                        )
                    except Exception:
                        pass
            logger.info("Migrated %d entries to global memory_index", len(seen))
    else:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_index (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)


def _migration_002_vec_store(conn: sqlite3.Connection, engine) -> None:
    """Create vector store tables (vec_entries virtual table + vec_meta).

    Requires sqlite-vec extension to be loaded.
    """
    # Load vec extension for the virtual table
    try:
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
    except Exception as e:
        logger.warning("sqlite-vec extension not available, vector store tables may not work: %s", e)

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
            embedding float[384] distance_metric=cosine
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            source_key TEXT NOT NULL DEFAULT '',
            exchange_idx INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_meta_source ON vec_meta (source, source_key)")
    logger.info("Vector store tables created")


def _migration_003_clusters(conn: sqlite3.Connection, engine) -> None:
    """Create topic clustering tables with proper FKs and indexes."""
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_clusters (
            cluster_id TEXT PRIMARY KEY,
            label TEXT NOT NULL DEFAULT '',
            keywords TEXT NOT NULL DEFAULT '[]',
            session_count INTEGER NOT NULL DEFAULT 0,
            exchange_count INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT NOT NULL DEFAULT '',
            last_updated TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 1.0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exchange_clusters (
            exchange_rowid INTEGER NOT NULL,
            cluster_id TEXT NOT NULL REFERENCES topic_clusters(cluster_id) ON DELETE CASCADE,
            similarity REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (exchange_rowid, cluster_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_relations (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            shared_keywords TEXT NOT NULL DEFAULT '[]',
            shared_count INTEGER NOT NULL DEFAULT 0,
            relationship_type TEXT NOT NULL DEFAULT 'related',
            weight REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (source_id, target_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exchange_clusters_cid ON exchange_clusters (cluster_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_relations_target ON topic_relations (target_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_clusters_updated ON topic_clusters (last_updated)")
    logger.info("Topic clustering tables created")


def _migration_004_entity_graph(conn: sqlite3.Connection, engine) -> None:
    """Create entity graph tables."""
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            mention_count INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_relations (
            source_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            PRIMARY KEY (source_id, target_id, relation_type)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities (entity_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities (name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_relations_target ON entity_relations (target_id)")
    logger.info("Entity graph tables created")


def _migration_005_entity_mentions(conn: sqlite3.Connection, engine) -> None:
    """Create entity_mentions bridge table linking entities to vec_meta."""
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_mentions (
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            exchange_rowid INTEGER NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            first_seen TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (entity_id, exchange_rowid)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_mentions_exchange ON entity_mentions (exchange_rowid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity ON entity_mentions (entity_id)")
    logger.info("Entity mentions table created")


def _migration_006_hash_dedup(conn: sqlite3.Connection, engine) -> None:
    """Add hash column to vec_meta for deduplication."""
    # Add column (safe: ALTER TABLE ADD COLUMN is idempotent with IF NOT EXISTS pattern)
    cursor = conn.execute("PRAGMA table_info(vec_meta)")
    cols = {r[1] for r in cursor.fetchall()}
    if "hash" not in cols:
        conn.execute("ALTER TABLE vec_meta ADD COLUMN hash TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_meta_hash ON vec_meta (hash)")
    logger.info("Hash dedup column added to vec_meta")


def _migration_007_vec_keywords(conn: sqlite3.Connection, engine) -> None:
    """Create vec_keywords table for fast keyword-based retrieval."""
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vec_keywords (
            rowid INTEGER NOT NULL,
            word TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (rowid, word)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vec_keywords_word
        ON vec_keywords (word)
    """)
    # Backfill: parse keywords from existing vec_meta.metadata JSON
    import json
    rows = conn.execute(
        "SELECT rowid, metadata FROM vec_meta WHERE metadata != '{}'"
    ).fetchall()
    inserted = 0
    for rowid, meta_json in rows:
        try:
            meta = json.loads(meta_json)
            kws = json.loads(meta.get("keywords", "[]"))
            for kw in kws:
                conn.execute(
                    "INSERT OR IGNORE INTO vec_keywords (rowid, word, score) VALUES (?, ?, ?)",
                    (rowid, kw["word"], kw["score"])
                )
                inserted += 1
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    conn.commit()
    logger.info("vec_keywords: %d rows inserted (backfill)", inserted)


def _migration_008_fix_indexes_fks(conn: sqlite3.Connection, engine) -> None:
    """Add missing indexes and FK constraints for performance and data integrity."""
    conn.execute("PRAGMA foreign_keys=ON")

    # Index on vec_keywords.word (critical for keyword_search performance)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vec_keywords_word
        ON vec_keywords (word)
    """)

    # Expression index for entity_search LOWER(e.name) queries
    # SQLite doesn't support expression indexes in older versions,
    # so we create a regular index and note that queries should avoid LOWER()
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_name_lower
        ON entities (name)
    """)

    # Index on entity_mentions for faster lookups
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_entity_mentions_exchange_rowid
        ON entity_mentions (exchange_rowid)
    """)

    logger.info("Missing indexes created")


def _migration_009_entity_dedup(conn: sqlite3.Connection, engine) -> None:
    """Add normalized_name column + unique index to prevent entity duplicates."""
    conn.execute("PRAGMA foreign_keys=ON")

    # Step 1: add column (safe: try/except)
    try:
        conn.execute("ALTER TABLE entities ADD COLUMN normalized_name TEXT")
    except sqlite3.OperationalError:
        pass

    # Step 2: backfill normalized_name for existing null rows
    conn.execute(
        "UPDATE entities SET normalized_name = LOWER(name) WHERE normalized_name IS NULL"
    )

    # Step 3: merge duplicates — for each (normalized_name, entity_type) group
    # with >1 row, keep the one with highest mention_count and re-point FK refs
    dupes = conn.execute("""
        SELECT normalized_name, entity_type
        FROM entities
        GROUP BY normalized_name, entity_type
        HAVING COUNT(*) > 1
    """).fetchall()

    for normalized_name, entity_type in dupes:
        keeper = conn.execute("""
            SELECT id
            FROM entities
            WHERE normalized_name = ? AND entity_type = ?
            ORDER BY mention_count DESC, last_seen DESC
            LIMIT 1
        """, (normalized_name, entity_type)).fetchone()
        keeper_id = keeper["id"]

        extra_ids = [
            r["id"] for r in conn.execute(
                "SELECT id FROM entities WHERE normalized_name = ? AND entity_type = ? AND id != ?",
                (normalized_name, entity_type, keeper_id),
            ).fetchall()
        ]

        extra_sum = conn.execute(
            "SELECT COALESCE(SUM(mention_count), 0) FROM entities WHERE id IN ({})".format(
                ",".join("?" for _ in extra_ids)
            ),
            extra_ids,
        ).fetchone()[0]

        conn.execute(
            "UPDATE entities SET mention_count = mention_count + ? WHERE id = ?",
            (extra_sum, keeper_id),
        )

        for eid in extra_ids:
            conn.execute("UPDATE OR IGNORE entity_relations SET source_id = ? WHERE source_id = ?", (keeper_id, eid))
            conn.execute("UPDATE OR IGNORE entity_relations SET target_id = ? WHERE target_id = ?", (keeper_id, eid))
            conn.execute("UPDATE OR IGNORE entity_mentions SET entity_id = ? WHERE entity_id = ?", (keeper_id, eid))

        placeholders = ",".join("?" for _ in extra_ids)
        conn.execute(f"DELETE FROM entities WHERE id IN ({placeholders})", extra_ids)

    # Step 4: create unique index to prevent future duplicates
    try:
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_dedup
            ON entities (normalized_name, entity_type)
        """)
    except sqlite3.OperationalError:
        pass

    logger.info("Entity dedup migration complete: merged %d groups", len(dupes))


def _migration_010_relevance_metadata(conn: sqlite3.Connection, engine) -> None:
    """Add relevance tracking columns to vec_meta, retrieval_log table, and weight to memory_index."""
    cursor = conn.execute("PRAGMA table_info(vec_meta)")
    cols = {r[1] for r in cursor.fetchall()}

    if "relevance_score" not in cols:
        conn.execute("ALTER TABLE vec_meta ADD COLUMN relevance_score REAL NOT NULL DEFAULT 0.5")
    if "query_count" not in cols:
        conn.execute("ALTER TABLE vec_meta ADD COLUMN query_count INTEGER NOT NULL DEFAULT 0")
    if "last_accessed" not in cols:
        conn.execute("ALTER TABLE vec_meta ADD COLUMN last_accessed TEXT NOT NULL DEFAULT ''")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vec_meta_relevance ON vec_meta (relevance_score DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vec_meta_accessed ON vec_meta (last_accessed)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT '',
            query TEXT NOT NULL DEFAULT '',
            vec_rowid INTEGER NOT NULL,
            fusion_score REAL NOT NULL DEFAULT 0.0,
            relevance_score REAL NOT NULL DEFAULT 0.0,
            rank INTEGER NOT NULL DEFAULT 0,
            retrieved_at TEXT NOT NULL DEFAULT (datetime('now')),
            source TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_retrieval_log_rowid ON retrieval_log (vec_rowid)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_retrieval_log_time ON retrieval_log (retrieved_at)
    """)

    try:
        conn.execute("ALTER TABLE memory_index ADD COLUMN weight REAL NOT NULL DEFAULT 1.0")
    except sqlite3.OperationalError:
        pass

    logger.info("Relevance metadata and retrieval_log added to vec_meta")


def _migration_012_content_hash(conn: sqlite3.Connection, engine) -> None:
    """Add content_hash column to vec_meta for efficient dedup."""
    cursor = conn.execute("PRAGMA table_info(vec_meta)")
    cols = {r[1] for r in cursor.fetchall()}
    if "content_hash" not in cols:
        conn.execute("ALTER TABLE vec_meta ADD COLUMN content_hash TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_meta_content_hash ON vec_meta(content_hash)")
    logger.info("content_hash column added to vec_meta")


def _migration_011_vec_keywords_covering_index(conn: sqlite3.Connection, engine) -> None:
    """Add covering index on (word, rowid, score) for keyword_search performance.

    The keyword_search query does:
        SELECT vk.rowid, SUM(vk.score) ... WHERE vk.word IN (?) GROUP BY vk.rowid ORDER BY score DESC

    A covering index on (word, rowid, score) lets SQLite answer the entire query
    from the index without touching the table.
    """
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vec_keywords_word_rowid_score
        ON vec_keywords (word, rowid, score)
    """)
    logger.info("Covering index idx_vec_keywords_word_rowid_score created on vec_keywords")


_MEMORY_MIGRATIONS = (
    _migration_001_global_memory_index,
    _migration_002_vec_store,
    _migration_003_clusters,
    _migration_004_entity_graph,
    _migration_005_entity_mentions,
    _migration_006_hash_dedup,
    _migration_007_vec_keywords,
    _migration_008_fix_indexes_fks,
    _migration_009_entity_dedup,
    _migration_010_relevance_metadata,
    _migration_011_vec_keywords_covering_index,
    _migration_012_content_hash,
)


async def init_memory_db() -> None:
    """Initialize memory.db: create tables and run pending migrations.

    Uses synchronous sqlite3 to avoid aiosqlite thread lifecycle issues.
    The connection is closed immediately after initialization.
    """
    db_path = resolve_memory_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        row = cursor.fetchone()
        current = 0
        if row:
            c2 = conn.execute("SELECT version FROM schema_version LIMIT 1")
            r = c2.fetchone()
            current = r["version"] if r else 0
        else:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")

        # Simple sync engine wrapper
        class _SyncEngine:
            def execute(self, c, sql, params=()):
                return c.execute(sql, params)
            def commit(self, c):
                c.commit()

        engine = _SyncEngine()

        async def _run_migrations():
            nonlocal current
            for version, migration in enumerate(_MEMORY_MIGRATIONS[current:], start=current + 1):
                migration(conn, engine)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                conn.commit()
                current = version

        import asyncio
        await _run_migrations()

        conn.commit()
        mark_initialized(db_path)
        logger.info("memory.db initialized at %s (migration v%s)", db_path, current)
    finally:
        conn.close()
