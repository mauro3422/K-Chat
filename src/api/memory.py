"""Memory API facade — re-exports for web/ layer consumption.

Architecture: web/ → src/api/ → src/memory/
The web layer must go through this facade instead of importing src/memory/ directly.
"""

import logging
import sqlite3
from contextlib import closing
from typing import Any, Callable

from src.memory.analysis.graph_analysis import EntityGraph
from src.memory.content_hash import content_hash
from src.memory.embedding_identity import session_exchange_embedding_identity
from src.memory.embeddings.service import generate_embeddings_batch
from src.memory.memory_db_path import resolve_memory_db_path


def memory_graph_snapshot(
    layer: str = "unified",
    *,
    db_path: str | None = None,
    graph_factory: Callable[[str], Any] = EntityGraph,
    connection_factory: Callable[[str], sqlite3.Connection] = sqlite3.connect,
) -> dict[str, Any]:
    """Build a framework-agnostic graph payload for the web facade."""

    resolved_db_path = db_path or resolve_memory_db_path()
    graph = graph_factory(resolved_db_path)
    graph.refresh()
    pmi_names = {
        name.lower()
        for entity_id, name in graph._names.items()
        if entity_id.startswith("pmi_")
    }

    nodes = []
    for name in graph._degree_centrality:
        normalized = name.lower()
        is_pmi = normalized in pmi_names
        if layer == "curated" and is_pmi:
            continue
        if layer == "pmi" and not is_pmi:
            continue
        nodes.append(
            {
                "id": name,
                "label": name.capitalize(),
                "pagerank": round(graph.pagerank(name), 6),
                "degree": round(graph.degree_centrality(name), 6),
                "hub": round(graph.hub_score(name), 6),
                "authority": round(graph.authority_score(name), 6),
                "community": graph.entity_community(name),
                "is_pmi": is_pmi,
            }
        )

    nodes.sort(key=lambda item: item["pagerank"], reverse=True)
    nodes = nodes[:100]
    allowed_nodes = {str(node["id"]).lower() for node in nodes}
    edges = []
    try:
        with closing(connection_factory(resolved_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT source_id, target_id, weight FROM entity_relations"):
                source_name = graph._names.get(str(row["source_id"]))
                target_name = graph._names.get(str(row["target_id"]))
                if not source_name or not target_name:
                    continue
                source = source_name.lower()
                target = target_name.lower()
                if source in allowed_nodes and target in allowed_nodes:
                    edges.append(
                        {
                            "source": source,
                            "target": target,
                            "weight": float(row["weight"] or 1.0),
                        }
                    )
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to load graph edges: %s", exc)

    return {"ok": True, "nodes": nodes, "edges": edges}


__all__ = [
    "content_hash",
    "session_exchange_embedding_identity",
    "generate_embeddings_batch",
    "memory_graph_snapshot",
]
