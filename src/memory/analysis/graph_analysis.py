"""Entity graph analysis — PageRank, centrality, and graph metrics.

Uses the curated memory DB's ``entity_relations`` and ``entities`` tables
to build a weighted undirected graph, then computes:

  - Degree centrality
  - PageRank (via networkx)
  - Eigenvector centrality (via networkx)

All functions return scores for entity names, not internal IDs.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional networkx dependency
# ---------------------------------------------------------------------------
try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    nx = None
    NETWORKX_AVAILABLE = False
    logger.warning("networkx not available — graph centrality will be empty")


# ---------------------------------------------------------------------------
# EntityGraph
# ---------------------------------------------------------------------------


class EntityGraph:
    """Entity relation graph loaded from ``kairos_curated_memory.db``.

    Caches PageRank, degree centrality, eigenvector centrality, HITS scores,
    and Louvain communities keyed by entity *name* (lowercased).

    Parameters
    ----------
    curated_db_path : str
        Path to ``memory/kairos_curated_memory.db``.
    """

    def __init__(self, curated_db_path: str) -> None:
        self._db_path = curated_db_path
        self._names: dict[str, str] = {}  # id → name
        self._pagerank: dict[str, float] = {}
        self._degree_centrality: dict[str, float] = {}
        self._eigenvector: dict[str, float] = {}
        self._hubs: dict[str, float] = {}
        self._authorities: dict[str, float] = {}
        self._communities: dict[str, int] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public scores
    # ------------------------------------------------------------------

    def pagerank(self, entity_name: str) -> float:
        """PageRank for an entity by name (0.0 if not found)."""
        self._ensure_loaded()
        return self._pagerank.get(entity_name.lower(), 0.0)

    def degree_centrality(self, entity_name: str) -> float:
        """Normalised degree centrality (0.0 if not found)."""
        self._ensure_loaded()
        return self._degree_centrality.get(entity_name.lower(), 0.0)

    def eigenvector_centrality(self, entity_name: str) -> float:
        """Eigenvector centrality (0.0 if not found or no networkx)."""
        self._ensure_loaded()
        return self._eigenvector.get(entity_name.lower(), 0.0)

    def hub_score(self, entity_name: str) -> float:
        """HITS Hub score (0.0 if not found or no networkx)."""
        self._ensure_loaded()
        return self._hubs.get(entity_name.lower(), 0.0)

    def authority_score(self, entity_name: str) -> float:
        """HITS Authority score (0.0 if not found or no networkx)."""
        self._ensure_loaded()
        return self._authorities.get(entity_name.lower(), 0.0)

    def entity_community(self, entity_name: str) -> int:
        """Louvain community index (-1 if not found)."""
        self._ensure_loaded()
        return self._communities.get(entity_name.lower(), -1)

    def max_centrality_for_any(self, names: list[str]) -> float:
        """Return the highest centrality score across a list of names.

        Useful for scoring a session containing several entities.
        """
        self._ensure_loaded()
        best = 0.0
        for name in names:
            best = max(best, self._pagerank.get(name.lower(), 0.0))
        return best

    def get_expanded_community_votes(self, names: list[str]) -> dict[int, float]:
        """Calculate weighted community votes for a list of entity names using graph neighbors."""
        self._ensure_loaded()
        votes: dict[int, float] = {}

        for raw_name in names:
            name = raw_name.lower()
            if name not in self._communities:
                continue

            # Base vote for the node's own community
            own_comm = self._communities[name]
            votes[own_comm] = votes.get(own_comm, 0.0) + 1.0

            # Spread fractional votes to neighbors if networkx graph is available
            if hasattr(self, "_nx_graph") and self._nx_graph is not None:
                if name in self._nx_graph:
                    neighbors = self._nx_graph[name]
                    for neighbor_name, edge_data in neighbors.items():
                        if neighbor_name in self._communities:
                            neighbor_comm = self._communities[neighbor_name]
                            weight = float(edge_data.get("weight", 1.0))
                            # Add a fraction of the weight as a vote
                            votes[neighbor_comm] = votes.get(neighbor_comm, 0.0) + (weight * 0.5)

        return votes

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Load entity relations from the curated DB and compute metrics.

        Gracefully handles missing tables or empty DB — returns empty
        scores instead of raising.
        """
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
        except Exception as exc:
            logger.debug("Entity graph: cannot connect to DB: %s", exc)
            self._loaded = True
            return

        # 1. Load entity names
        names: dict[str, str] = {}
        try:
            for row in conn.execute("SELECT id, name FROM entities"):
                names[str(row["id"])] = str(row["name"])
        except Exception as exc:
            logger.debug("Entity graph: entities table unavailable: %s", exc)
            conn.close()
            self._loaded = True
            return
        self._names = names

        # 2. Load relations as weighted edges
        edges: list[tuple[str, str, float]] = []
        try:
            for row in conn.execute(
                "SELECT source_id, target_id, weight FROM entity_relations"
            ):
                src = str(row["source_id"])
                tgt = str(row["target_id"])
                wt = float(row["weight"] or 1.0)
                if src in names and tgt in names:
                    edges.append((names[src].lower(), names[tgt].lower(), wt))
        except Exception as exc:
            logger.debug("Entity graph: entity_relations table unavailable: %s", exc)

        conn.close()

        if not edges:
            logger.info("Entity graph: no edges loaded")
            self._loaded = True
            return

        # 3. Build networkx graph
        if NETWORKX_AVAILABLE and nx is not None:
            G = nx.Graph()
            self._nx_graph = G
            for src_name, tgt_name, wt in edges:
                G.add_edge(src_name, tgt_name, weight=wt)

            # Degree centrality
            deg = nx.degree_centrality(G)
            self._degree_centrality = {
                str(node).lower(): float(score) for node, score in deg.items()
            }

            # PageRank
            try:
                pr = nx.pagerank(G, weight="weight", alpha=0.85, max_iter=100, tol=1e-6)
                self._pagerank = {
                    str(node).lower(): float(score) for node, score in pr.items()
                }
            except Exception as exc:
                logger.warning("PageRank computation failed: %s", exc)
                self._pagerank = {}

            # HITS
            try:
                hubs, auths = nx.hits(G, max_iter=100)
                self._hubs = {str(node).lower(): abs(float(score)) for node, score in hubs.items()}
                self._authorities = {str(node).lower(): abs(float(score)) for node, score in auths.items()}
            except Exception as exc:
                logger.warning("HITS computation failed: %s", exc)
                self._hubs = {}
                self._authorities = {}

            # Louvain Communities
            try:
                from networkx.algorithms.community import louvain_communities
                communities_list = louvain_communities(G, weight="weight")
                self._communities = {}
                for idx, community_nodes in enumerate(communities_list):
                    for node in community_nodes:
                        self._communities[str(node).lower()] = idx
            except Exception as exc:
                logger.warning("Louvain community detection failed: %s", exc)
                self._communities = {}

            # Eigenvector centrality — try iterative first (handles disconnected graphs)
            try:
                ev = nx.eigenvector_centrality(G, weight="weight", max_iter=100)
                self._eigenvector = {
                    str(node).lower(): float(score) for node, score in ev.items()
                }
            except Exception:
                try:
                    ev = nx.eigenvector_centrality_numpy(G, weight="weight", max_iter=100)
                    self._eigenvector = {
                        str(node).lower(): float(score) for node, score in ev.items()
                    }
                except Exception:
                    self._eigenvector = {}
        else:
            # Fallback: degree-only from edge count
            degree: dict[str, int] = {}
            for src_name, tgt_name, _ in edges:
                degree[src_name] = degree.get(src_name, 0) + 1
                degree[tgt_name] = degree.get(tgt_name, 0) + 1
            n = len(degree)
            self._degree_centrality = {
                node: count / max(n - 1, 1) for node, count in degree.items()
            }
            self._pagerank = {}
            self._eigenvector = {}
            self._hubs = {}
            self._authorities = {}
            self._communities = {}
            self._nx_graph = None

        logger.info(
            "Entity graph loaded: %d entities, %d edges",
            len(self._degree_centrality),
            len(edges),
        )
        self._loaded = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()

    def __repr__(self) -> str:
        return f"EntityGraph(nodes={len(self._degree_centrality)})"
