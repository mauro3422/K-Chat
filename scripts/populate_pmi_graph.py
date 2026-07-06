"""
PMI Injection Script v4 — IDF + Stemming + Edge-IDF + Community Detection
==========================================================================

Four algorithmic filters (zero hardcoded dictionaries beyond STOP):
1. Node IDF: downweights words that appear in many sessions
2. Edge IDF: downweights pairs that co-occur across many sessions (generic connections)
3. Spanish stemming: groups morphological variants without embeddings
4. Community detection: prunes nodes that bridge unrelated communities (noise hubs)
"""

import sqlite3
import math
import time
import random
from collections import defaultdict
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.analysis.pmi_relations import (
    calculate_pmi_for_session,
    persist_pmi_relations,
    stem_spanish,
)
from src.memory.analysis.corpus import STOP
from src.memory.analysis.pmi_relations import SPANISH_STOPWORDS


# ── IDF ──────────────────────────────────────────────────────────────────────

def compute_idf(df: dict[str, int], N: int) -> dict[str, float]:
    """Smoothed IDF: log((N+1)/(df+1)) + 1."""
    return {w: math.log((N + 1) / (d + 1)) + 1.0 for w, d in df.items()}


# ── Graph: Clustering Coefficient ─────────────────────────────────────────────

def compute_local_clustering(
    relations: list[tuple[str, str, float]],
) -> dict[str, float]:
    """Local clustering coefficient per node."""
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b, _ in relations:
        adj[a].add(b)
        adj[b].add(a)

    clustering: dict[str, float] = {}
    for node, neighbors in adj.items():
        k = len(neighbors)
        if k < 2:
            clustering[node] = 0.0
            continue
        neighbors_list = list(neighbors)
        edges_between = 0
        for i in range(len(neighbors_list)):
            ni = neighbors_list[i]
            for j in range(i + 1, len(neighbors_list)):
                if neighbors_list[j] in adj[ni]:
                    edges_between += 1
        max_possible = k * (k - 1) / 2
        clustering[node] = edges_between / max_possible if max_possible > 0 else 0.0

    return clustering


# ── Graph: Label Propagation Community Detection ──────────────────────────────

def label_propagation(
    adj: dict[str, set[str]],
    max_iter: int = 20,
    seed: int = 42,
) -> dict[str, int]:
    """Greedy label propagation for community detection (no networkx needed).
    
    Each node adopts the majority label of its neighbors.
    Converges in < 10 iterations for typical graphs.
    """
    nodes = list(adj.keys())
    random.seed(seed)
    
    # Initialize: each node is its own community
    labels = {node: i for i, node in enumerate(nodes)}
    
    for _ in range(max_iter):
        changed = False
        random.shuffle(nodes)
        for node in nodes:
            neighbors = adj.get(node, set())
            if not neighbors:
                continue
            
            # Count neighbor labels
            label_counts: dict[int, int] = defaultdict(int)
            for neighbor in neighbors:
                label_counts[labels[neighbor]] += 1
            
            # Adopt most common label
            most_common = max(label_counts, key=label_counts.get)
            if labels[node] != most_common:
                labels[node] = most_common
                changed = True
        
        if not changed:
            break
    
    return labels


def compute_participation_coefficient(
    adj: dict[str, set[str]],
    communities: dict[str, int],
) -> dict[str, float]:
    """Participation coefficient: how much a node bridges communities.
    
    PC ≈ 0 → node stays within its community (signal)
    PC ≈ 1 → node connects many communities equally (noise hub)
    """
    pc: dict[str, float] = {}
    for node, neighbors in adj.items():
        k = len(neighbors)
        if k == 0:
            pc[node] = 0.0
            continue
        
        # Count degree per community
        comm_degrees: dict[int, int] = defaultdict(int)
        for neighbor in neighbors:
            comm = communities.get(neighbor, -1)
            comm_degrees[comm] += 1
        
        pc[node] = 1.0 - sum((d / k) ** 2 for d in comm_degrees.values())
    
    return pc


# ── Pruning ───────────────────────────────────────────────────────────────────

def prune_noise_hubs(
    relations: list[tuple[str, str, float]],
    clustering: dict[str, float],
    participation: dict[str, float],
    degree: dict[str, int],
    cc_threshold: float = 0.04,
    pc_threshold: float = 0.70,
    degree_threshold: int = 40,
) -> list[tuple[str, str, float]]:
    """Remove relations involving noise hubs.
    
    A noise hub has:
    - Low clustering (scattered neighbors)
    - High participation coefficient (bridges communities)
    - High degree (connects many nodes)
    """
    noise_nodes: set[str] = set()
    
    for node in degree:
        deg = degree[node]
        cc = clustering.get(node, 0.0)
        pc_val = participation.get(node, 0.0)
        
        # Type A: low clustering + high degree (classic noise hub)
        if deg >= degree_threshold and cc < cc_threshold:
            noise_nodes.add(node)
        
        # Type B: high participation + high degree (community bridge)
        if deg >= degree_threshold and pc_val > pc_threshold:
            noise_nodes.add(node)

    if noise_nodes:
        print(f"\n🧹 Graph pruning: removing {len(noise_nodes)} noise hubs...")
        # Sort by degree to show worst offenders
        sorted_noise = sorted(noise_nodes, key=lambda n: -degree.get(n, 0))
        for node in sorted_noise[:12]:
            print(f"   ✂️  {node:25s} deg={degree[node]:4d}  CC={clustering.get(node,0):.4f}  PC={participation.get(node,0):.3f}")

    return [(a, b, w) for a, b, w in relations 
            if a not in noise_nodes and b not in noise_nodes]


# ── Main Pipeline ────────────────────────────────────────────────────────────

def run():
    t0 = time.time()
    db_path = resolve_memory_db_path()

    MIN_OCCURRENCES = 3
    DF_MAX_RATIO = 0.35
    CC_THRESHOLD = 0.04
    PC_THRESHOLD = 0.70
    DEGREE_THRESHOLD = 40

    # ═══════════════════════════════════════════════════════════════════
    # 1. CLEAR
    # ═══════════════════════════════════════════════════════════════════
    print("🧹 Clearing curated DB...")
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM entity_relations")
    conn.execute("DELETE FROM entity_mentions")
    conn.execute("DELETE FROM entities")
    conn.execute("DELETE FROM concept_canonical")
    try:
        conn.execute("DELETE FROM vec_concepts")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print("   DB cleared.")

    # ═══════════════════════════════════════════════════════════════════
    # 2. LOAD MESSAGES
    # ═══════════════════════════════════════════════════════════════════
    print("\n📂 Loading messages...")
    conn_sess = sqlite3.connect("memory/kairos_memory.db")
    cursor = conn_sess.cursor()
    cursor.execute(
        "SELECT session_id, content FROM messages WHERE role IN ('user', 'assistant')"
    )
    rows = cursor.fetchall()
    conn_sess.close()

    sessions_data: dict[str, list[str]] = {}
    for sid, content in rows:
        if not str(content).startswith("[SYSTEM:"):
            sessions_data.setdefault(sid, []).append(content)

    active_sessions = {sid: msgs for sid, msgs in sessions_data.items() if msgs}
    total_sessions = len(active_sessions)
    total_messages = sum(len(msgs) for msgs in active_sessions.values())
    print(f"   {total_sessions} sessions, {total_messages} messages loaded.")

    # ═══════════════════════════════════════════════════════════════════
    # 3. EXTRACT + STEM + COMPUTE NODE DF
    # ═══════════════════════════════════════════════════════════════════
    print("\n🔤 Extracting tokens + stemming...")
    all_raw_tokens: set[str] = set()
    raw_to_stem: dict[str, str] = {}
    stem_df: dict[str, int] = defaultdict(int)
    stem_occurrences: dict[str, int] = defaultdict(int)

    for sid, msgs in active_sessions.items():
        session_stems: set[str] = set()
        for msg in msgs:
            clean = (
                msg.replace(",", " ")
                .replace(".", " ")
                .replace("?", " ")
                .replace(":", " ")
                .replace('"', " ")
                .replace("'", " ")
            )
            for word in clean.split():
                t = word.strip().lower()
                if (
                    t not in STOP
                    and t not in SPANISH_STOPWORDS
                    and len(t) > 2
                    and t.isalpha()
                ):
                    all_raw_tokens.add(t)
                    stem = stem_spanish(t)
                    raw_to_stem[t] = stem
                    session_stems.add(stem)
        for s in session_stems:
            stem_df[s] += 1

    # Compute occurrences
    for sid, msgs in active_sessions.items():
        for msg in msgs:
            clean = (
                msg.replace(",", " ")
                .replace(".", " ")
                .replace("?", " ")
                .replace(":", " ")
                .replace('"', " ")
                .replace("'", " ")
            )
            for word in clean.split():
                t = word.strip().lower()
                if t in raw_to_stem:
                    stem_occurrences[raw_to_stem[t]] += 1

    raw_count = len(all_raw_tokens)
    unique_stems = len(stem_df)
    print(f"   {raw_count} raw → {unique_stems} stems "
          f"({unique_stems / max(raw_count, 1) * 100:.1f}%)")

    # ═══════════════════════════════════════════════════════════════════
    # 4. NODE IDF
    # ═══════════════════════════════════════════════════════════════════
    print("\n📊 Computing node IDF...")
    node_idf = compute_idf(dict(stem_df), total_sessions)
    max_node_idf = math.log(total_sessions + 1) + 1.0
    print(f"   IDF range: [{min(node_idf.values()):.2f}, {max(node_idf.values()):.2f}]")

    # ═══════════════════════════════════════════════════════════════════
    # 5. FILTER STEMS
    # ═══════════════════════════════════════════════════════════════════
    max_df = max(3, int(total_sessions * DF_MAX_RATIO))
    print(f"\n🔍 Filtering (occ ≥ {MIN_OCCURRENCES}, DF ≤ {max_df})...")

    survivors: set[str] = set()
    blocked_rare = 0
    blocked_df_high = 0

    for stem, df_val in stem_df.items():
        occ = stem_occurrences.get(stem, 0)
        if occ < MIN_OCCURRENCES:
            blocked_rare += 1
            continue
        if df_val > max_df:
            blocked_df_high += 1
            continue
        survivors.add(stem)

    passed = len(survivors)
    print(f"   Blocked occ<{MIN_OCCURRENCES}: {blocked_rare}")
    print(f"   Blocked DF>{max_df}:    {blocked_df_high}")
    print(f"   ✅ Survivors:       {passed} ({passed / max(unique_stems, 1) * 100:.1f}%)")

    # Build stem_map
    stem_map: dict[str, str] = {}
    for raw in all_raw_tokens:
        stem_map[raw] = raw_to_stem.get(raw, raw)

    # ═══════════════════════════════════════════════════════════════════
    # 6. PMI EXTRACTION + EDGE-DF TRACKING
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n⚡ PMI extraction ({total_sessions} sessions) + edge-DF tracking...")
    t_pmi = time.time()
    total_relations: list[tuple[str, str, float]] = []
    edge_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)

    for idx, (sid, msgs) in enumerate(active_sessions.items(), 1):
        rels, pairs = calculate_pmi_for_session(
            msgs,
            min_cooccurrences=1,
            pmi_threshold=1.0,
            word_idf=node_idf,
            max_idf=max_node_idf,
            stem_map=stem_map,
        )
        total_relations.extend(rels)
        for pair in pairs:
            edge_sessions[pair].add(sid)
        
        if idx % 5 == 0 or idx == total_sessions:
            print(f"   [{idx:2d}/{total_sessions}] {sid[:12]}... → "
                  f"{len(rels):4d} rels, {len(pairs):4d} pairs "
                  f"(total rels: {len(total_relations):6d})")

    pmi_time = time.time() - t_pmi
    print(f"\n   PMI done in {pmi_time:.1f}s — {len(total_relations)} relations")

    # ═══════════════════════════════════════════════════════════════════
    # 7. EDGE IDF
    # ═══════════════════════════════════════════════════════════════════
    print("\n📐 Computing edge-IDF...")
    edge_df = {pair: len(sessions) for pair, sessions in edge_sessions.items()}
    edge_idf = {}
    for pair, df_val in edge_df.items():
        edge_idf[pair] = math.log((total_sessions + 1) / (df_val + 1)) + 1.0

    max_edge_idf = max(edge_idf.values()) if edge_idf else 1.0
    edge_idf_values = list(edge_idf.values())
    edge_idf_values.sort()
    print(f"   Edge-IDF range: [{edge_idf_values[0]:.2f}, {edge_idf_values[-1]:.2f}]")
    print(f"   Pairs with edge-IDF < 1.0 (generic): "
          f"{sum(1 for v in edge_idf_values if v < 1.0)} / {len(edge_idf_values)}")

    # Apply edge-IDF multiplier to relations
    print("   Applying edge-IDF multiplier to relations...")
    for i, (a, b, w) in enumerate(total_relations):
        pair = tuple(sorted([a, b]))
        eidf = edge_idf.get(pair, max_edge_idf)
        edge_mult = max(0.4, eidf / max_edge_idf)  # floor at 0.4
        total_relations[i] = (a, b, w * edge_mult)

    # ═══════════════════════════════════════════════════════════════════
    # 8. POST-PMI GRAPH PRUNING (CC + PC)
    # ═══════════════════════════════════════════════════════════════════
    if total_relations:
        # Build adjacency
        adj: dict[str, set[str]] = defaultdict(set)
        degree: dict[str, int] = defaultdict(int)
        for a, b, _ in total_relations:
            adj[a].add(b)
            adj[b].add(a)
            degree[a] += 1
            degree[b] += 1

        # Clustering coefficient
        print("\n🔬 Computing clustering coefficients...")
        t_cc = time.time()
        clustering = compute_local_clustering(total_relations)
        print(f"   Done in {time.time() - t_cc:.1f}s")

        # Community detection + participation coefficient
        print("🧩 Running label propagation community detection...")
        t_comm = time.time()
        communities = label_propagation(adj)
        num_communities = len(set(communities.values()))
        print(f"   Found {num_communities} communities in {time.time() - t_comm:.1f}s")

        print("📊 Computing participation coefficients...")
        t_pc = time.time()
        participation = compute_participation_coefficient(adj, communities)
        print(f"   Done in {time.time() - t_pc:.1f}s")
        
        # PC stats
        pc_values = list(participation.values())
        print(f"   PC range: [{min(pc_values):.3f}, {max(pc_values):.3f}]")
        print(f"   High PC (> {PC_THRESHOLD}): {sum(1 for v in pc_values if v > PC_THRESHOLD)} nodes")
        print(f"   Low CC (< {CC_THRESHOLD}):  {sum(1 for v in clustering.values() if v < CC_THRESHOLD)} nodes")

        # Prune
        before = len(total_relations)
        total_relations = prune_noise_hubs(
            total_relations, clustering, participation, degree,
            CC_THRESHOLD, PC_THRESHOLD, DEGREE_THRESHOLD,
        )
        after = len(total_relations)
        if before != after:
            print(f"   Pruned {before - after} relations ({(before - after) / max(before, 1) * 100:.1f}%)")

    # ═══════════════════════════════════════════════════════════════════
    # 9. PERSIST
    # ═══════════════════════════════════════════════════════════════════
    if total_relations:
        print("\n💾 Persisting...")
        written = persist_pmi_relations(db_path, total_relations)
        print(f"   {written} relations written.")
    else:
        print("\n⚠️  No relations!")
        return

    # ═══════════════════════════════════════════════════════════════════
    # 10. BENCHMARK
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print("📈 BENCHMARK RESULTS — v4 (IDF + Stem + Edge-IDF + Communities)")
    print(f"{'=' * 60}")

    conn = sqlite3.connect(db_path)
    entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    rel_count = conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0]

    signal_rows = conn.execute("""
        SELECT e.name, COUNT(*) as deg, ROUND(AVG(er.weight), 2) as avg_w
        FROM entities e
        JOIN entity_relations er ON e.id = er.source_id OR e.id = er.target_id
        GROUP BY e.id
        HAVING deg >= 3 AND avg_w >= 0.8
        ORDER BY deg DESC
    """).fetchall()

    weight_dist = conn.execute("""
        SELECT 
            CASE 
                WHEN weight >= 1.5 THEN '1.5-2.0 (strong)'
                WHEN weight >= 1.0 THEN '1.0-1.5 (medium)'
                WHEN weight >= 0.6 THEN '0.6-1.0 (weak)'
                ELSE '< 0.6 (noise)'
            END as bucket,
            COUNT(*) as cnt
        FROM entity_relations
        GROUP BY bucket
        ORDER BY MIN(weight) DESC
    """).fetchall()

    typos_in_db = conn.execute("""
        SELECT COUNT(*) FROM entities 
        WHERE name IN ('veras', 'tenes', 'deberia', 'dan', 'aveces', 'muchas', 
                       'funcionan', 'vrias', 'algun', 'ocurrio', 'qiue', 'auqe')
    """).fetchone()[0]

    generic_noise = conn.execute("""
        SELECT COUNT(*) FROM entities 
        WHERE name IN ('mas', 'tenemos', 'mejor', 'realmente', 'pasa', 'tienen',
                       'actual', 'dentro', 'veamos', 'tenes', 'ellos', 'creo',
                       'corre', 'tiempo', 'uso', 'cosa')
    """).fetchone()[0]

    core_concepts = conn.execute("""
        SELECT name, (SELECT COUNT(*) FROM entity_relations 
                      WHERE source_id = e.id OR target_id = e.id) as deg
        FROM entities e
        WHERE name IN ('llm', 'openclaw', 'arquitectur', 'modelo', 'grafo', 
                       'widget', 'embed', 'curator', 'curador', 'agent', 
                       'hermes', 'sandbox', 'entity', 'api', 'svg',
                       'ifram', 'reddit', 'discord', 'skill', 'nativ', 
                       'gecko', 'nanobot', 'trigg', 'secur', 'protocol',
                       'cluster', 'vector', 'patron', 'herramient', 'prototip')
        ORDER BY deg DESC
    """).fetchall()

    conn.close()
    total_time = time.time() - t0

    signal_pct = len(signal_rows) / max(entity_count, 1) * 100
    noise_pct = typos_in_db / max(entity_count, 1) * 100
    core_found = len(core_concepts)

    print(f"\n⏱️  Total time: {total_time:.1f}s")
    print(f"\n📦 Volume:")
    print(f"   Entities:          {entity_count}")
    print(f"   Relations:         {rel_count}")

    print(f"\n🎯 Signal quality:")
    print(f"   Signal (deg≥3, w≥0.8): {len(signal_rows)} ({signal_pct:.1f}%)")
    print(f"   Generic noise entities: {generic_noise}")
    print(f"   Typos in DB:            {typos_in_db}")
    print(f"   Core concepts found:    {core_found}/25+")

    print(f"\n🧬 Stemming:")
    print(f"   Raw → stem: {raw_count} → {unique_stems} "
          f"({unique_stems / max(raw_count, 1) * 100:.1f}%)")

    print(f"\n🛡️  Filters applied:")
    print(f"   Node IDF:       weight × min(idf_a, idf_b) / {max_node_idf:.1f}")
    print(f"   Edge IDF:       weight × edge_idf / {max_edge_idf:.1f}")
    print(f"   Occ < {MIN_OCCURRENCES}:        {blocked_rare} stems blocked")
    print(f"   DF > {max_df}:           {blocked_df_high} stems blocked")
    print(f"   Graph pruning:  CC<{CC_THRESHOLD} | PC>{PC_THRESHOLD}, deg≥{DEGREE_THRESHOLD}")

    print(f"\n📊 Weight distribution:")
    for bucket, cnt in weight_dist:
        bar_len = max(1, cnt * 40 // max(rel_count, 1))
        bar = "█" * bar_len
        print(f"   {bucket:25s}: {cnt:6d} {bar}")

    print(f"\n🏆 Top signal entities:")
    for i, (name, deg, avg_w) in enumerate(signal_rows[:25], 1):
        flag = ""
        if name in ('mas', 'tenemos', 'mejor', 'pasa', 'tienen', 'realmente', 
                     'actual', 'tenes', 'veamos', 'creo', 'corre', 'tiempo', 'uso', 'cosa'):
            flag = " ⚠️"
        print(f"   {i:2d}. {name:25s}  deg={deg:4d}  avg_w={avg_w}{flag}")

    if core_concepts:
        print(f"\n💎 Core K-Chat concepts in graph:")
        for name, deg in core_concepts[:15]:
            print(f"   {name:25s}  deg={deg}")

    print(f"\n{'=' * 60}")
    print("✅ v4 Benchmark complete.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Populate PMI knowledge graph from chat history")
    parser.add_argument("--db", default=None, help="Path to kairos_memory.db (default: auto-detect)")
    parser.add_argument("--curated-db", default=None, help="Path to curated memory DB (default: auto-detect)")
    parser.add_argument("--quiet", action="store_true", help="Suppress benchmark output")
    args = parser.parse_args()
    
    if args.db:
        import os
        os.environ["KAIROS_SESSIONS_DB_PATH"] = args.db
    if args.curated_db:
        os.environ["KAIROS_MEMORY_DB_PATH"] = args.curated_db
    
    run()
