#!/usr/bin/env python3
"""Benchmark: test the memory pipeline with real session data.

Usage:
    cd /home/maurol/dev/K-Chat && venv/bin/python3 scripts/benchmark_memory.py [--sessions N]

Shows:
- What keywords, entities, and clusters get extracted from real sessions
- Hybrid search results for sample queries
- Signal breakdown (vector vs keyword vs entity)
- Pipeline timing
"""

import asyncio
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    args = set(sys.argv[1:])
    max_sessions = 0
    for arg in args:
        if arg.startswith("--sessions="):
            max_sessions = int(arg.split("=")[1])
        elif arg.startswith("--queries="):
            pass  # handled later

    print("=" * 60)
    print("K-Chat Memory Pipeline Benchmark")
    print("=" * 60)

    # ── 1. Init DB ──────────────────────────────────────────────────
    from src.memory.memory_schema import init_memory_db
    t0 = time.time()
    await init_memory_db()
    print(f"\n[1/5] DB initialized ({time.time()-t0:.1f}s)")

    # ── 2. Get sessions ─────────────────────────────────────────────
    from src.memory.vectorize_sessions import get_all_sessions
    sessions = await get_all_sessions()
    if max_sessions > 0:
        sessions = sessions[:max_sessions]
    print(f"\n[2/5] Sessions: {len(sessions)} encontradas")
    for s in sessions:
        sid = s["session_id"]
        name = s.get("name", "") or "(sin nombre)"
        print(f"  - {sid[:12]}... {name}")

    # ── 3. Vectorize sessions ───────────────────────────────────────
    from src.memory.vectorize_sessions import vectorize_session
    from src.memory.clustering.heuristic import HeuristicClusterer
    from src.memory.entity.linker import EntityLinker

    t0 = time.time()
    total_ex = total_noise = total_ents = 0
    for s in sessions[:3]:  # Max 3 sessions for speed
        sid = s["session_id"]
        clusterer = HeuristicClusterer()
        linker = EntityLinker()
        count, noise, mappings, ents = await vectorize_session(
            sid, clusterer=clusterer, linker=linker
        )
        total_ex += count
        total_noise += noise
        total_ents += len(ents)
        print(f"\n[3/5] Sesion {sid[:12]}...: {count} exchanges, {noise} noise, {len(ents)} con entidades")

        # Show sample extractions from first 3 exchanges
        from src.memory.vectorize_sessions import get_session_messages, group_into_exchanges
        msgs = await get_session_messages(sid)
        excs = group_into_exchanges(msgs)
        for i, ex in enumerate(excs[:3]):
            from src.memory.keywords.extractor import extract_keywords
            from src.memory.entity.extractor import extract_entities
            kws = extract_keywords(ex["text"], top_k=3)
            ents = extract_entities(ex["text"])
            kws_str = ", ".join(w for w, _ in kws) if kws else "(ninguna)"
            ents_str = ", ".join(f"{n}({t})" for t, n, _ in ents) if ents else "(ninguna)"
            print(f"  Exchange {i+1}: KW=[{kws_str}]  ENT=[{ents_str}]")

    print(f"\n[3/5] Total: {total_ex} exchanges, {total_noise} noise ({time.time()-t0:.1f}s)")

    # ── 4. Test hybrid search ───────────────────────────────────────
    from src.memory.memory_db_path import resolve_memory_db_path
    from src.memory.retrieval.hybrid_retriever import HybridRetriever

    db_path = resolve_memory_db_path()
    retriever = HybridRetriever(db_path)

    test_queries = [
        "async tools fix",
        "widgets interactivos",
        "streaming pipeline",
        "entity graph",
        "testing de herramientas",
    ]

    print(f"\n[4/5] Hybrid Search ({len(test_queries)} queries)")
    t0 = time.time()
    for q in test_queries:
        results = await retriever.search(q, top_k=3)
        signals = []
        for r in results:
            parts = []
            if r.vector_score > 0.3:
                parts.append(f"V{int(r.vector_score*100)}%")
            if r.keyword_score > 0:
                parts.append(f"K{round(r.keyword_score,2)}")
            if r.entity_score > 0:
                parts.append(f"E{int(r.entity_score)}")
            sig = ",".join(parts)
            label = f" [#{r.rank} {sig}]" if sig else ""
            preview = r.text[:100].replace("\n", " | ")
            signals.append(f"   {label} {preview}")
        print(f"\n  Query: {q}")
        for s in signals:
            print(s)

    retriever.close()
    print(f"\n[4/5] Search done ({time.time()-t0:.1f}s)")

    # ── 5. Stats ────────────────────────────────────────────────────
    import sqlite3
    conn = sqlite3.connect(db_path)
    tables = [
        ("vec_meta", "embeddings"),
        ("vec_keywords", "keywords"),
        ("entities", "entidades"),
        ("entity_relations", "relaciones entidad"),
        ("entity_mentions", "menciones entidad"),
        ("topic_clusters", "clusters"),
        ("exchange_clusters", "mappings exchange-to-cluster"),
    ]
    print(f"\n[5/5] DB Stats")
    for table, desc in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:25s} ({desc:22s}): {count}")
        except Exception:
            print(f"  {table:25s} ({desc:22s}): (no existe)")
    conn.close()

    print(f"\n{'=' * 60}")
    print("Benchmark complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
