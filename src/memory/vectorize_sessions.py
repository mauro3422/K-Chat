"""One-time script + library: vectorize all existing session exchanges.

Can be run standalone:  python3 -m src.memory.vectorize_sessions
Or imported:           await vectorize_all_sessions()
"""

import asyncio
import json
import logging
import sys
from typing import Any, Optional

import aiosqlite

# Reuse the jaccard function from clustering module
from src.memory.clustering.heuristic import jaccard_similarity
from src.memory.content_hash import normalize_for_content_hash
from src.memory.embedding_identity import session_exchange_embedding_identity

logger = logging.getLogger(__name__)


def _normalize_for_dedup(text: str) -> str:
    """Normalize text before hashing: lowercase, collapse whitespace, strip code blocks."""
    return normalize_for_content_hash(text)


async def get_all_sessions(repos: Any = None) -> list[dict[str, Any]]:
    """Get all sessions from sessions.db.

    Accepts an optional *repos* object (from src.memory.repos). When *repos* is
    provided, uses its connection pool; otherwise opens a standalone connection
    (used by the CLI entry point).
    """
    if repos is not None:
        conn = await repos.sessions._get_conn()
        cursor = await conn.execute(
            "SELECT session_id, name, created_at FROM sessions ORDER BY created_at ASC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # Standalone fallback — open the sessions DB directly.
    from src.memory.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        cursor = await conn.execute(
            "SELECT session_id, name, created_at FROM sessions ORDER BY created_at ASC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def get_session_messages(session_id: str, repos: Any = None) -> list[dict[str, Any]]:
    """Get all messages for a session.

    Accepts an optional *repos* object (from src.memory.repos). When *repos* is
    provided, uses its connection pool; otherwise opens a standalone connection.
    """
    if repos is not None:
        conn = await repos.messages._get_conn()
        cursor = await conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # Standalone fallback.
    from src.memory.db_path import resolve_db_path
    db_path = resolve_db_path()
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        cursor = await conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()


def group_into_exchanges(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group messages into user+assistant exchanges.

    Each exchange = a user message + the assistant response that follows.
    """
    exchanges = []
    current_user = None

    for msg in messages:
        role = msg["role"]
        content = (msg["content"] or "").strip()
        if not content:
            continue

        if role == "user":
            current_user = {"user_text": content, "assistant_text": "", "created_at": msg.get("created_at", "")}
        elif role == "assistant" and current_user is not None:
            current_user["assistant_text"] = content
            exchanges.append({
                "text": f"User: {current_user['user_text']}\nAssistant: {content}",
                "created_at": current_user["created_at"],
            })
            current_user = None

    # Orphan user messages (no assistant response yet)
    if current_user is not None:
        exchanges.append({
            "text": f"User: {current_user['user_text']}\nAssistant: _pending_",
            "created_at": current_user["created_at"],
        })

    return exchanges

async def vectorize_exchange(exchange: dict[str, Any], session_id: str, idx: int,
                              clusterer: Any = None,
                              store: Any = None,
                              embedding: Optional[list[float]] = None,
                              *,
                              source_node_id: str = "") -> dict[str, Any] | None:
    """Pipeline completo FASE 7 para un exchange: keywords → noise filter → embed → cluster.

    Pipeline:
      1. Extraer keywords (TF-IDF)
      2. Noise filter heurístico → si es noise, se saltea (ahorra embedding + storage)
      3. Generar embedding (fastembed) y guardar en sqlite-vec
      4. Asignar a topic cluster (Jaccard similarity)

    Args:
        exchange: El exchange a procesar.
        session_id: ID de la sesión.
        idx: Índice del exchange dentro de la sesión.
        clusterer: Clusterer heurístico (opcional).
        store: VectorStore inyectado por DI. Si es None, crea uno propio (fallback).
        embedding: Embedding pre-computado (desde batch). Si se pasa, saltea
            generate_embedding individual.
        source_node_id: Origin node stamp for the embedding row. Empty string
            falls back to the active coordinator's node_id.

    Returns:
        Dict con metadata del exchange procesado, o None si es noise.
        Si no es noise, incluye 'rowid' (para exchange_clusters mapping) y 'cluster_similarity'.
    """
    import hashlib
    from src.memory.memory_db_path import resolve_memory_db_path
    from src.memory.embeddings.service import generate_embedding
    from src.memory.vector.store import VectorStore
    from src.memory.keywords.extractor import extract_keywords, add_to_global_corpus
    from src.memory.noise_filter import is_noise
    from src.memory.entity.extractor import extract_entities, learn_from_text

    text = exchange["text"]
    if len(text) < 30:
        return None

    # Step 1: Extract keywords (TF-IDF)
    kws = extract_keywords(text, top_k=5)
    kw_json = json.dumps([{"word": w, "score": round(s, 3)} for w, s in kws])

    # Step 2: Noise filter → skip early si es ruido (ahorra embedding + storage)
    noise, reason = is_noise(text)

    # Step 2.5: Extract entities (for knowledge graph)
    entities = extract_entities(text) if not noise else []
    learn_from_text(text)

    if noise:
        return {
            "rowid": None,
            "keywords": [w for w, _ in kws],
            "noise": True,
            "reason": reason,
            "cluster_id": None,
            "cluster_similarity": 0.0,
            "entities": entities,
        }

    # Feed real text to global TF-IDF corpus (improves IDF over time)
    add_to_global_corpus(text)

    # Step 2.6: Hash dedup — evitar embed/storage si el texto ya se vectorizó
    text_hash = hashlib.md5(_normalize_for_dedup(text[:4000]).encode()).hexdigest()

    own_store = False
    if store is None:
        store = VectorStore(resolve_memory_db_path())
        own_store = True

    if not source_node_id:
        from src.memory.provenance import resolve_local_node_id
        source_node_id = resolve_local_node_id()

    # Check against DB first (persistent dedup via content_hash)
    try:
        conn = store._get_conn()
        existing = conn.execute(
            "SELECT rowid FROM vec_meta WHERE content_hash = ?", (text_hash,)
        ).fetchone()
        if existing is not None:
            existing_rowid = existing[0]
            if own_store:
                store.close()
            return {
                "rowid": existing_rowid,
                "keywords": [w for w, _ in kws],
                "noise": False,
                "reason": "",
                "cluster_id": None,
                "cluster_similarity": 0.0,
                "entities": entities,
                "dedup": True,
            }
    except Exception:
        pass  # Column might not exist yet — fall through

    metadata = {
        "created_at": exchange.get("created_at", ""),
        "keywords": kw_json,
        "noise": False,
        "noise_reason": "",
    }
    try:
        if embedding is not None:
            vec = embedding
        else:
            vec = await asyncio.to_thread(generate_embedding, text[:4000])
        rowid = store.insert(
            vec,
            source="session",
            source_key=session_id,
            exchange_idx=idx,
            text=text[:4000],
            metadata=metadata,
            hash=text_hash,
            content_hash=text_hash,
            source_node_id=source_node_id,
        )
        # Step 3.5: Write keywords to vec_keywords for keyword search
        if rowid and kws:
            try:
                conn = store._get_conn()
                for word, score in kws:
                    conn.execute(
                        "INSERT OR IGNORE INTO vec_keywords (rowid, word, score) VALUES (?, ?, ?)",
                        (rowid, word, round(score, 3))
                    )
                conn.commit()
            except Exception:
                pass  # Non-fatal: vec_keywords might not exist yet
    finally:
        if own_store:
            store.close()

    # Step 4: Assign to topic cluster
    assigned_cluster = None
    cluster_similarity = 0.0
    if kws and clusterer is not None:
        cluster = clusterer.assign_from_keyword_list(kws, session_id)
        assigned_cluster = cluster.id
        # clusterer doesn't track per-exchange similarity, but we can
        # compute Jaccard between the exchange keywords and cluster centroid
        cluster_similarity = jaccard_similarity(
            {w for w, _ in kws},
            cluster.keyword_set,
        )

    return {
        "rowid": rowid,
        "keywords": [w for w, _ in kws],
        "noise": False,
        "reason": "",
        "cluster_id": assigned_cluster,
        "cluster_similarity": cluster_similarity,
        "entities": entities,
    }


def _get_last_vectorized_idx(store: Any, session_id: str) -> int:
    """Query vec_meta for the max exchange_idx already stored for this session.
    
    Returns -1 if none exist (meaning process all exchanges).
    """
    conn = store._get_conn()
    row = conn.execute(
        "SELECT COALESCE(MAX(exchange_idx), -1) FROM vec_meta WHERE source='session' AND source_key=?",
        (session_id,)
    ).fetchone()
    return row[0] if row else -1


def _get_work_catalog(repos: Any = None) -> Any:
    if repos is not None and getattr(repos, "memory", None) is not None:
        catalog = getattr(repos.memory, "work_catalog", None)
        if catalog is not None:
            return catalog
    try:
        from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
        return MemoryWorkCatalogRepository()
    except Exception:
        logger.debug("memory_work_catalog unavailable", exc_info=True)
        return None


def _catalog_is_processed(catalog: Any, session_id: str, idx: int, text_hash: str) -> bool:
    if catalog is None:
        return False
    identity = session_exchange_embedding_identity()
    try:
        return bool(catalog.is_processed(
            source="session",
            source_key=session_id,
            item_idx=idx,
            content_hash=text_hash,
            **identity.as_catalog_kwargs(),
        ))
    except Exception:
        logger.debug("Failed to read memory work catalog", exc_info=True)
        return False


def _catalog_mark(
    catalog: Any,
    session_id: str,
    idx: int,
    text_hash: str,
    status: str,
    *,
    vec_rowid: int | None = None,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    if catalog is None:
        return
    identity = session_exchange_embedding_identity()
    try:
        catalog.mark(
            source="session",
            source_key=session_id,
            item_idx=idx,
            content_hash=text_hash,
            status=status,
            vec_rowid=vec_rowid,
            reason=reason,
            metadata=metadata,
            source_node_id=metadata.get("source_node_id", "") if metadata else "",
            **identity.as_catalog_kwargs(),
        )
    except Exception:
        logger.debug("Failed to write memory work catalog", exc_info=True)


async def vectorize_session(session_id: str, dry_run: bool = False,
                            clusterer: Any = None, repos: Any = None,
                            store: Any = None,
                            linker: Any = None,
                            exchange_indexes: list[int] | set[int] | None = None,
                            *,
                            source_node_id: str = "") -> tuple[int, int, list[dict[str, Any]], list[list[tuple[str, str, float]]]]:
    """Vectorize all exchanges in a single session.

    Pipeline completo por exchange: keywords → noise filter → embed → cluster.
    Los embeddings se generan en batch (todos los exchanges no-noise en una sola
    llamada al modelo) para aprovechar el batching interno de fastembed (3-5x más rápido).

    Args:
        store: VectorStore inyectado (desde DI). Si es None, crea uno propio.
        linker: EntityLinker opcional. Si se pasa, linkea las entidades al grafo.
        source_node_id: Origin node for the embeddings written by this call.
            Empty string falls back to the active coordinator's node_id
            (via ``resolve_local_node_id``), or stays empty when no
            coordinator is configured.

    Returns:
        (count, noise_count, exchange_cluster_mappings, entities_list)
        exchange_cluster_mappings: list of {exchange_rowid, cluster_id, similarity}
          for persisting the exchange→cluster link.
        entities_list: list of entity lists per non-noise exchange.
    """
    import hashlib
    import json
    from src.memory.embeddings.service import generate_embeddings_batch
    from src.memory.keywords.extractor import extract_keywords, add_to_global_corpus
    from src.memory.noise_filter import is_noise
    from src.memory.entity.extractor import extract_entities

    messages = await get_session_messages(session_id, repos=repos)
    exchanges = group_into_exchanges(messages)
    target_indexes = set(exchange_indexes) if exchange_indexes is not None else None

    if dry_run:
        if target_indexes is None:
            return len(exchanges), 0, [], []
        return len([idx for idx in range(len(exchanges)) if idx in target_indexes]), 0, [], []

    count = 0
    noise_count = 0
    mappings: list[dict[str, Any]] = []
    entities_list: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    own_store = False
    if store is None:
        from src.memory.memory_db_path import resolve_memory_db_path
        from src.memory.vector.store import VectorStore
        store = VectorStore(resolve_memory_db_path())
        own_store = True

    if not source_node_id:
        from src.memory.provenance import resolve_local_node_id
        source_node_id = resolve_local_node_id()

    try:
        last_idx = _get_last_vectorized_idx(store, session_id)
        catalog = _get_work_catalog(repos)

        # ── Phase 1: Extract metadata, collect candidates for batch embedding ──
        candidates: list[tuple[int, dict[str, Any], str, str, list[tuple[str, float]], list]] = []

        for idx, exchange in enumerate(exchanges):
            if target_indexes is not None and idx not in target_indexes:
                continue
            if catalog is None and idx <= last_idx:
                continue
            try:
                text = exchange["text"]
                text_hash = hashlib.md5(_normalize_for_dedup(text[:4000]).encode()).hexdigest()
                if target_indexes is None and _catalog_is_processed(catalog, session_id, idx, text_hash):
                    continue
                if len(text) < 30:
                    noise_count += 1
                    _catalog_mark(
                        catalog,
                        session_id,
                        idx,
                        text_hash,
                        "noise",
                        reason="short_text",
                        metadata={"source_node_id": source_node_id},
                    )
                    continue

                kws = extract_keywords(text, top_k=5)
                kw_json = json.dumps([{"word": w, "score": round(s, 3)} for w, s in kws])

                noise, reason = is_noise(text)
                entities = extract_entities(text) if not noise else []

                if noise:
                    noise_count += 1
                    _catalog_mark(
                        catalog,
                        session_id,
                        idx,
                        text_hash,
                        "noise",
                        reason=reason,
                        metadata={"keywords": [w for w, _ in kws], "source_node_id": source_node_id},
                    )
                    continue

                add_to_global_corpus(text)

                # Check against DB first (persistent dedup via content_hash)
                try:
                    existing = store._get_conn().execute(
                        "SELECT rowid FROM vec_meta WHERE content_hash = ?", (text_hash,)
                    ).fetchone()
                    if existing is not None:
                        existing_rowid = existing[0]
                        _catalog_mark(
                            catalog,
                            session_id,
                            idx,
                            text_hash,
                            "deduped",
                            vec_rowid=existing_rowid,
                            reason="content_hash",
                            metadata={"keywords": [w for w, _ in kws], "source_node_id": source_node_id},
                        )
                        logger.debug("Hash collision — skipping duplicate exchange (hash=%s)", text_hash[:12])
                        count += 1
                        entities_list.append({
                            "entities": entities,
                            "keywords": [w for w, _ in kws],
                        })
                        if linker is not None and entities:
                            linker.link_exchange(
                                entities, session_id,
                                exchange_rowid=existing_rowid,
                                exchange_text=text,
                            )
                        continue
                except Exception:
                    pass  # Column might not exist yet — fall through

                # Then check in-memory set
                if text_hash in seen_hashes:
                    _catalog_mark(
                        catalog,
                        session_id,
                        idx,
                        text_hash,
                        "deduped",
                        reason="batch_content_hash",
                        metadata={"keywords": [w for w, _ in kws], "source_node_id": source_node_id},
                    )
                    count += 1
                    logger.debug("In-memory hash collision — skipping (hash=%s)", text_hash[:12])
                    continue
                seen_hashes.add(text_hash)

                candidates.append((idx, exchange, text_hash, kw_json, kws, entities))

            except Exception as e:
                logger.warning("Failed to prepare exchange %d of %s: %s", idx, session_id, e)
                noise_count += 1

        # ── Phase 2: Batch embed + insert ──
        if candidates:
            texts_to_embed = [exchange["text"][:4000] for _, exchange, _, _, _, _ in candidates]
            vectors = await asyncio.to_thread(generate_embeddings_batch, texts_to_embed)

            for (idx, exchange, text_hash, kw_json, kws, entities), vec in zip(candidates, vectors):
                try:
                    metadata = {
                        "created_at": exchange.get("created_at", ""),
                        "keywords": kw_json,
                        "noise": False,
                        "noise_reason": "",
                    }
                    rowid = store.insert(
                        vec,
                        source="session",
                        source_key=session_id,
                        exchange_idx=idx,
                        text=exchange["text"][:4000],
                        metadata=metadata,
                        hash=text_hash,
                        content_hash=text_hash,
                        source_node_id=source_node_id,
                    )
                    _catalog_mark(
                        catalog,
                        session_id,
                        idx,
                        text_hash,
                        "embedded",
                        vec_rowid=rowid,
                        metadata={"keywords": [w for w, _ in kws], "source_node_id": source_node_id},
                    )

                    if rowid and kws:
                        try:
                            conn = store._get_conn()
                            for word, score in kws:
                                conn.execute(
                                    "INSERT OR IGNORE INTO vec_keywords (rowid, word, score) VALUES (?, ?, ?)",
                                    (rowid, word, round(score, 3)),
                                )
                            conn.commit()
                        except Exception:
                            logger.warning("Failed to insert keywords for exchange", exc_info=True)

                    count += 1
                    entities_list.append({
                        "entities": entities,
                        "keywords": [w for w, _ in kws],
                    })

                    if linker is not None and entities:
                        linker.link_exchange(
                            entities, session_id,
                            exchange_rowid=rowid,
                            exchange_text=exchange["text"],
                        )

                    if kws and clusterer is not None:
                        cluster = clusterer.assign_from_keyword_list(kws, session_id)
                        cluster_similarity = jaccard_similarity(
                            {w for w, _ in kws},
                            cluster.keyword_set,
                        )
                        if cluster.id and rowid:
                            mappings.append({
                                "exchange_rowid": rowid,
                                "cluster_id": cluster.id,
                                "similarity": cluster_similarity,
                            })

                except Exception as e:
                    logger.warning(
                        "Failed to insert vectorized exchange %d of %s: %s",
                        idx, session_id, e,
                    )
                    noise_count += 1

    finally:
        if own_store:
            store.close()

    return count, noise_count, mappings, entities_list


async def vectorize_all_sessions(dry_run: bool = False, max_sessions: int = 0,
                                 repos: Any = None,
                                 linker: Any = None,
                                 *,
                                 source_node_id: str = "") -> dict[str, int]:
    """Vectorize ALL sessions with the complete FASE 7 pipeline.

    Pipeline global:
      1. Por sesión: get_messages → group_into_exchanges → vectorize_session
      2. Por exchange: keywords → noise filter → embed → cluster → entity extraction
      3. Al final: flush clusters + exchange_clusters + detect relations + entity graph → persistir en DB

    Args:
        linker: EntityLinker opcional. Si es None y no es dry_run, se crea uno nuevo.
        source_node_id: Origin node stamp for embeddings and graphs written
            by this run. Empty string falls back to the active coordinator's
            node_id via ``resolve_local_node_id()``.

    Returns:
        {session_id: exchanges_processed_count}
    """
    from src.memory.clustering.heuristic import HeuristicClusterer, flush_clusters_to_db
    from src.memory.clustering.relations import detect_relations, flush_relations_to_db
    from src.memory.memory_db_path import resolve_memory_db_path
    from src.memory.entity.linker import EntityLinker

    sessions = await get_all_sessions(repos=repos)
    if max_sessions > 0:
        sessions = sessions[:max_sessions]

    clusterer = HeuristicClusterer()
    if linker is None and not dry_run:
        linker = EntityLinker(db_path=resolve_memory_db_path())

    if not source_node_id:
        from src.memory.provenance import resolve_local_node_id
        source_node_id = resolve_local_node_id()

    all_mappings: list[dict[str, Any]] = []
    results: dict[str, int] = {}
    total_exchanges = 0
    total_noise = 0

    for session in sessions:
        sid = session["session_id"]

        if dry_run:
            messages = await get_session_messages(sid, repos=repos)
            exchanges = group_into_exchanges(messages)
            count = len(exchanges)
            noise_count = 0
        else:
            count, noise_count, mappings, _entities = await vectorize_session(
                sid, dry_run=False, clusterer=clusterer, repos=repos, linker=linker,
                source_node_id=source_node_id,
            )
            all_mappings.extend(mappings)

        if count > 0:
            results[sid] = count
        total_exchanges += count
        total_noise += noise_count
        logger.info("Session %s: %d exchanges (%d noise) %s",
                    sid, count, noise_count,
                    "[DRY RUN]" if dry_run else "[VECTORIZED]")

    # Flush clusters + exchange mappings + relations to DB
    if not dry_run and clusterer.clusters:
        db_path = resolve_memory_db_path()
        c_count = await flush_clusters_to_db(clusterer, db_path, mappings=all_mappings, origin_node_id=source_node_id)
        logger.info("Flushed %d clusters + %d exchange mappings to DB",
                    c_count, len(all_mappings))
        cluster_dicts = [c.as_dict for c in clusterer.clusters.values()]
        relations = detect_relations(cluster_dicts)
        if relations:
            r_count = await flush_relations_to_db(relations, db_path)
            logger.info("Flushed %d relations to DB", r_count)

    # Flush entity graph
    if not dry_run and linker is not None and (linker.get_entities() or linker.get_relations()):
        db_path = resolve_memory_db_path()
        from src.memory.entity.linker import (
            flush_entities_to_db, flush_relations_to_db, flush_entity_mentions_to_db,
        )
        e_count = await flush_entities_to_db(linker, db_path, origin_node_id=source_node_id)
        r_count = await flush_relations_to_db(linker, db_path)
        m_count = await flush_entity_mentions_to_db(linker, db_path)
        logger.info("Flushed %d entities + %d relations + %d mentions to DB",
                    e_count, r_count, m_count)

    logger.info("Total: %d sessions, %d exchanges (%d noise) %s",
                len(results), total_exchanges, total_noise,
                "[DRY RUN]" if dry_run else "[VECTORIZED]")
    return results


# ── Standalone entry point ─────────────────────────────────────────

async def _main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args or "-n" in args
    max_sessions = 0
    for arg in args:
        if arg.startswith("--max="):
            max_sessions = int(arg.split("=")[1])
        elif arg.startswith("--limit="):
            max_sessions = int(arg.split("=")[1])

    print(f"{'🔍 DRY RUN' if dry_run else '🚀 VECTORIZANDO'} sesiones...")
    results = await vectorize_all_sessions(dry_run=dry_run, max_sessions=max_sessions)

    total = sum(results.values())
    print(f"\n✅ {len(results)} sesiones, {total} exchanges totales.")
    if dry_run:
        print("   Pasa sin --dry-run para guardar los embeddings.")

    from src.memory.vector.store import VectorStore
    from src.memory.memory_db_path import resolve_memory_db_path
    store = VectorStore(resolve_memory_db_path())
    print(f"   Total vectores en store: {store.count()}")
    store.close()


if __name__ == "__main__":
    asyncio.run(_main())
