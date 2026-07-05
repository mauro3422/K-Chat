"""Semantic similarity against curated memory via embeddings.

Computes cosine similarity between session/candidate text and the 24 curated
memory entries in ``kairos_curated_memory.db`` using fastembed (ONNX) and
sqlite-vec for efficient nearest-neighbor queries.

Gracefully degrades to 0.0 if dependencies are not available.

Two loading strategies (tried in order):
  1. sqlite-vec virtual table (fast, efficient) — connection is cached
     module-wide to avoid repeated open/close cycles.
  2. In-memory cosine similarity against all curated vectors (fallback).

NOTES
-----
- Per-keyword semantic queries are deliberately NOT supported.  Similarity
  only makes sense at the document/session level.  Use ``max_similarity``
  once per session to get a novelty score, then factor it into the candidate
  confidence formula (see ``scoring.py``).
- The vec0 connection is cached at module level (``_VEC0_CONN``).  It is
  opened once with ``check_same_thread=False`` and reused across queries.
  Call ``close_vec0()`` if you need to explicitly release it.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------

try:
    from src.memory.embeddings.service import (
        EmbeddingService,
        EMBEDDING_DIM,
    )

    EMBEDDING_AVAILABLE = True
except ImportError:
    EmbeddingService = None  # type: ignore
    EMBEDDING_DIM = 384
    EMBEDDING_AVAILABLE = False
    logger.info("fastembed not available — semantic similarity disabled")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VEC0_SO_PATH: str | None = None
_VEC0_CONN: sqlite3.Connection | None = None


def _find_vec0_so() -> str | None:
    """Locate ``vec0`` shared library once and cache the path.

    Search order:
      1. ``sqlite_vec.loadable_path()`` — the canonical API (lib name only,
         ``dlopen`` resolves the ``.so`` extension on Linux).
      2. ``sqlite_vec.__file__`` parent directory — fallback for macOS/Windows
         where ``dlopen`` may need the full extension.
      3. Hardcoded venv path (last resort, fragile).

    Returns ``None`` when not found anywhere.
    """
    global _VEC0_SO_PATH
    if _VEC0_SO_PATH is not None:
        return _VEC0_SO_PATH if _VEC0_SO_PATH else None

    # Strategy 1: sqlite_vec.loadable_path() — the canonical location
    try:
        import sqlite_vec  # type: ignore[import-untyped]

        path = sqlite_vec.loadable_path()
        # On Linux, dlopen(3) appends ".so" implicitly
        if os.path.exists(path) or os.path.exists(path + ".so"):
            _VEC0_SO_PATH = path
            return _VEC0_SO_PATH
    except ImportError:
        pass

    # Strategy 2: walk the sqlite_vec package directory
    try:
        import sqlite_vec  # type: ignore[import-untyped]

        so_dir = Path(sqlite_vec.__file__).parent  # type: ignore[arg-type]
        for candidate in so_dir.iterdir():
            if candidate.name.startswith("vec0"):
                _VEC0_SO_PATH = str(candidate)
                return _VEC0_SO_PATH
    except (ImportError, AttributeError):
        pass

    # Strategy 3: hardcoded venv path (works in this project)
    candidates = [
        Path(__file__).resolve().parents[3]
        / "venv/lib/python3.14/site-packages/sqlite_vec/vec0.so",
    ]
    for so in candidates:
        if so.exists():
            _VEC0_SO_PATH = str(so)
            return _VEC0_SO_PATH

    _VEC0_SO_PATH = ""  # marker: not found
    return None


def _get_vec0_connection(db_path: str) -> sqlite3.Connection | None:
    """Return a cached vec0-enabled connection (opens it once)."""
    global _VEC0_CONN
    if _VEC0_CONN is not None:
        return _VEC0_CONN
    so_path = _find_vec0_so()
    if not so_path:
        return None
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.enable_load_extension(True)
        conn.load_extension(so_path)
        _VEC0_CONN = conn
        return conn
    except Exception as exc:
        logger.debug("sqlite-vec load failed: %s", exc)
        return None


def close_vec0() -> None:
    """Explicitly close the cached vec0 connection (e.g., for testing)."""
    global _VEC0_CONN, _VEC0_SO_PATH
    if _VEC0_CONN is not None:
        try:
            _VEC0_CONN.close()
        except Exception:
            pass
        _VEC0_CONN = None
    _VEC0_SO_PATH = None  # force re-discovery on next open


def _load_curated_vectors(
    db_path: str,
) -> tuple[list[list[float]], list[str]]:
    """Load all curated memory vectors into memory as fallback.

    Loads vec0 first so ``vec_entries`` (a vec0 virtual table) is readable.
    If vec0 cannot be loaded, returns empty lists.

    Returns (vectors, texts) where each vector is a list of floats.
    """
    vectors: list[list[float]] = []
    texts: list[str] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.enable_load_extension(True)
        so_path = _find_vec0_so()
        if so_path:
            try:
                conn.load_extension(so_path)
            except Exception as exc:
                logger.debug(
                    "vec0 load failed for fallback read: %s — no vectors available",
                    exc,
                )
                conn.close()
                return vectors, texts
        else:
            conn.close()
            return vectors, texts

        rows = conn.execute(
            """
            SELECT v.embedding, vm.text
            FROM vec_entries v
            JOIN vec_meta vm ON v.rowid = vm.rowid
            WHERE vm.source = 'memory'
            """
        ).fetchall()
        for row in rows:
            raw = row[0]
            if isinstance(raw, bytes):
                vec = json.loads(raw.decode("utf-8"))
            elif isinstance(raw, str):
                vec = json.loads(raw)
            else:
                continue
            if isinstance(vec, list) and len(vec) == EMBEDDING_DIM:
                vectors.append([float(x) for x in vec])
                texts.append(str(row[1] or ""))
        conn.close()
        logger.info(
            "In-memory fallback: loaded %d curated vectors (%d-dim)",
            len(vectors),
            EMBEDDING_DIM,
        )
    except Exception as exc:
        logger.debug("Failed to load curated vectors: %s", exc)
    return vectors, texts


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(ai * bi for ai, bi in zip(a, b))
    na = math.sqrt(sum(ai * ai for ai in a))
    nb = math.sqrt(sum(bi * bi for bi in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# SemanticSimilarity
# ---------------------------------------------------------------------------


class SemanticSimilarity:
    """Compute similarity of text against curated memory entries.

    Parameters
    ----------
    curated_db_path : str
        Path to ``memory/kairos_curated_memory.db``.
    embedding_service : EmbeddingService | None
        An optional pre-configured embedding service. If None, a new one
        is created on first use.
    cache_size : int
        Max number of similarity results to cache (LRU).  Default 1024.
    """

    def __init__(
        self,
        curated_db_path: str,
        embedding_service: Optional[Any] = None,
        cache_size: int = 1024,
    ) -> None:
        self._db_path = curated_db_path
        self._embedding_service = embedding_service
        self._own_service = embedding_service is None
        self._memory_count: int = 0
        self._loaded = False
        self._enabled = EMBEDDING_AVAILABLE

        # Strategy selection
        self._use_vec0 = False
        self._fallback_vectors: list[list[float]] = []
        self._fallback_texts: list[str] = []

        if not self._enabled:
            logger.info("SemanticSimilarity disabled (fastembed not available)")
        else:
            # Try vec0 first (cached global connection), fall back to in-memory
            test_conn = _get_vec0_connection(curated_db_path)
            if test_conn is not None:
                self._use_vec0 = True
                logger.info("SemanticSimilarity: using sqlite-vec (fast path, cached conn)")
            else:
                vectors, texts = _load_curated_vectors(curated_db_path)
                if vectors:
                    self._fallback_vectors = vectors
                    self._fallback_texts = texts
                    logger.info(
                        "SemanticSimilarity: using in-memory fallback (%d vectors)",
                        len(vectors),
                    )
                else:
                    self._enabled = False
                    logger.info(
                        "SemanticSimilarity disabled (no vec0 + no in-memory vectors)"
                    )

        # Dict cache for text → similarity results
        self._cache: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def max_similarity(self, text: str) -> float:
        """Return the highest cosine similarity of *text* against any curated memory entry.

        High similarity → text is semantically close to known memory.
        Low similarity → potentially novel information.

        Results are cached by text hash to avoid repeated embedding + query.
        Returns 0.0 if embedding dependencies are not available.
        """
        if not self._enabled:
            return 0.0

        # Cache lookup by text hash
        text_hash = hash(text[:4096])
        cached = self._cache.get(text_hash)
        if cached is not None:
            return cached

        vector = self._embed(text)
        if vector is None or all(v == 0.0 for v in vector):
            self._cache[text_hash] = 0.0
            return 0.0

        sim = self._query_nearest(vector)
        self._cache[text_hash] = sim
        return sim

    def closest_memory(self, text: str) -> dict[str, Any]:
        """Return the closest matching memory entry with distance and text.

        Returns empty dict if embedding is unavailable.
        """
        result: dict[str, Any] = {"distance": 1.0, "text": "", "source_key": ""}
        if not self._enabled:
            return result

        vector = self._embed(text)
        if vector is None:
            return result

        if self._use_vec0:
            conn = _get_vec0_connection(self._db_path)
            if conn is None:
                return result
            try:
                formatted = json.dumps(vector)
                row = conn.execute(
                    """
                    SELECT v.distance, vm.text, vm.source_key
                    FROM vec_entries v
                    JOIN vec_meta vm ON v.rowid = vm.rowid
                    WHERE vm.source = 'memory'
                      AND v.embedding MATCH ?
                    ORDER BY v.distance ASC
                    LIMIT 1
                    """,
                    (formatted,),
                ).fetchone()
                if row:
                    result["distance"] = float(row[0])
                    result["text"] = str(row[1] or "")[:200]
                    result["source_key"] = str(row[2] or "")
            except Exception as exc:
                logger.debug("vec_entries query failed: %s", exc)
        else:
            best_sim = -1.0
            best_idx = -1
            for i, fv in enumerate(self._fallback_vectors):
                sim = _cosine_similarity(vector, fv)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i
            if best_idx >= 0:
                result["distance"] = round(1.0 - best_sim, 4)
                result["text"] = self._fallback_texts[best_idx][:200]
        return result

    @property
    def memory_entry_count(self) -> int:
        self._ensure_loaded()
        return self._memory_count

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._memory_count = max(len(self._fallback_vectors), 0)
            if self._memory_count <= 0:
                try:
                    conn = sqlite3.connect(self._db_path)
                    row = conn.execute(
                        "SELECT COUNT(*) FROM vec_meta WHERE source='memory'"
                    ).fetchone()
                    self._memory_count = int(row[0]) if row else 0
                    conn.close()
                except Exception:
                    self._memory_count = 0
            self._loaded = True

    def _get_embedding_service(self) -> Any:
        if self._embedding_service is None and EMBEDDING_AVAILABLE:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    def _embed(self, text: str) -> Optional[list[float]]:
        svc = self._get_embedding_service()
        if svc is None:
            return None
        try:
            return svc.generate_embedding(text[:4096])
        except Exception as exc:
            logger.debug("Embedding generation failed: %s", exc)
            return None

    def _query_nearest(self, vector: list[float]) -> float:
        if self._use_vec0:
            conn = _get_vec0_connection(self._db_path)
            if conn is None:
                return 0.0
            try:
                formatted = json.dumps(vector)
                row = conn.execute(
                    """
                    SELECT v.distance
                    FROM vec_entries v
                    JOIN vec_meta vm ON v.rowid = vm.rowid
                    WHERE vm.source = 'memory'
                      AND v.embedding MATCH ?
                    ORDER BY v.distance ASC
                    LIMIT 1
                    """,
                    (formatted,),
                ).fetchone()
                if row:
                    # distance=0 means identical, distance=2 means opposite
                    return max(0.0, 1.0 - float(row[0]))
                return 0.0
            except Exception as exc:
                logger.debug("vec_entries query failed: %s", exc)
                return 0.0
        else:
            # In-memory fallback
            best_sim = 0.0
            for fv in self._fallback_vectors:
                sim = _cosine_similarity(vector, fv)
                if sim > best_sim:
                    best_sim = sim
            return best_sim
