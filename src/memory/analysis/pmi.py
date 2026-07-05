"""Pointwise Mutual Information (PMI) clustering for term associations.

PMI measures how much more often two terms co-occur than would be expected
by chance:

    PMI(w1, w2) = log(P(w1,w2) / (P(w1) * P(w2)))

Clusters are formed by linking term pairs with PMI above a threshold,
producing a term-association graph that reveals semantic groupings.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from src.memory.analysis.corpus import tokenize_doc

logger = logging.getLogger(__name__)


class PMIClustering:
    """PMI-based term association graph from session summary artifacts.

    Parameters
    ----------
    artifacts_root : str | Path
        Project root directory — scans ``memory/*/*/*/session--*.md``.
    pmi_threshold : float
        Minimum PMI to consider a pair meaningfully associated (default 2.0).
    min_df : int
        Minimum document frequency for a term to be included (default 2).
    """

    def __init__(
        self,
        artifacts_root: str | Path,
        pmi_threshold: float = 2.0,
        min_df: int = 2,
    ) -> None:
        self._root = Path(artifacts_root)
        self._threshold = pmi_threshold
        self._min_df = min_df
        self._pmi_scores: dict[tuple[str, str], float] = {}
        self._clusters: list[set[str]] = []
        self._term_cluster_map: dict[str, int] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def pmi_scores(self) -> dict[tuple[str, str], float]:
        self._ensure_loaded()
        return dict(self._pmi_scores)

    @property
    def clusters(self) -> list[set[str]]:
        self._ensure_loaded()
        return list(self._clusters)

    def cluster_of(self, term: str) -> int | None:
        """Return cluster index for *term*, or None if unclustered."""
        self._ensure_loaded()
        return self._term_cluster_map.get(term.lower())

    def pmi(self, term_a: str, term_b: str) -> float:
        """Return PMI score for a term pair (0.0 if below threshold / absent)."""
        self._ensure_loaded()
        key = tuple(sorted([term_a.lower(), term_b.lower()]))
        return self._pmi_scores.get(key, 0.0)

    def max_pmi_for_term(self, term: str) -> float:
        """Best PMI score any pair involving *term* attains."""
        self._ensure_loaded()
        t = term.lower()
        best = 0.0
        for (a, b), score in self._pmi_scores.items():
            if a == t or b == t:
                best = max(best, score)
        return best

    def cluster_cohesion(self, term: str) -> float:
        """Average PMI of *term* with other members of its cluster (0 if alone)."""
        self._ensure_loaded()
        t = term.lower()
        idx = self._term_cluster_map.get(t)
        if idx is None:
            return 0.0
        cluster = self._clusters[idx]
        if len(cluster) <= 1:
            return 0.0
        scores = []
        for other in cluster:
            if other == t:
                continue
            key = tuple(sorted([t, other]))
            scores.append(self._pmi_scores.get(key, 0.0))
        return sum(scores) / len(scores) if scores else 0.0

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Scan artifacts, compute co-occurrence matrix, PMI, and cluster."""
        logger.info("Refreshing PMI clustering from session summary artifacts …")

        # 1. Count documents and co-occurrences
        doc_term_sets: list[set[str]] = []
        term_df: Counter[str] = Counter()

        for path in sorted(self._root.glob("memory/*/*/*/session--*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Cannot read %s: %s", path, exc)
                continue
            tokens = tokenize_doc(text)
            unique = set(tokens)
            doc_term_sets.append(unique)
            for term in unique:
                term_df[term] += 1

        N = len(doc_term_sets)
        if N < 2:
            logger.info("PMI: not enough documents (%d) for meaningful co-occurrence", N)
            self._loaded = True
            return

        # 2. Filter to terms with min_df
        valid_terms = {term for term, df in term_df.items() if df >= self._min_df}
        # Filter doc term sets
        doc_term_sets = [ts & valid_terms for ts in doc_term_sets if ts & valid_terms]
        N = len(doc_term_sets)
        if N < 2:
            logger.info("PMI: fewer than 2 valid documents after filtering")
            self._loaded = True
            return

        # 3. Co-occurrence matrix (within sliding context window = document)
        cooc: dict[tuple[str, str], int] = defaultdict(int)
        for ts in doc_term_sets:
            sorted_terms = sorted(ts)  # deterministic order
            for i, a in enumerate(sorted_terms):
                for b in sorted_terms[i + 1 :]:
                    key = tuple(sorted([a, b]))
                    cooc[key] += 1

        # 4. Compute PMI for each pair
        pmi_scores: dict[tuple[str, str], float] = {}
        for (a, b), cooc_count in cooc.items():
            p_ab = cooc_count / N
            p_a = term_df[a] / N
            p_b = term_df[b] / N
            if p_a > 0 and p_b > 0 and p_ab > 0:
                pmi = math.log(p_ab / (p_a * p_b))
                if pmi >= self._threshold:
                    pmi_scores[(a, b)] = round(pmi, 4)

        self._pmi_scores = pmi_scores
        logger.info(
            "PMI: %d term pairs above threshold %.1f (vocab=%d, docs=%d)",
            len(pmi_scores),
            self._threshold,
            len(valid_terms),
            N,
        )

        # 5. Cluster: union-find on high-PMI pairs
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for a, b in pmi_scores:
            union(a, b)

        # Collect clusters
        clusters_map: dict[str, set[str]] = defaultdict(set)
        for term in valid_terms:
            root = find(term)
            clusters_map[root].add(term)

        self._clusters = [terms for terms in clusters_map.values() if len(terms) >= 2]
        # Sort clusters by size (descending)
        self._clusters.sort(key=len, reverse=True)
        self._term_cluster_map = {}
        for idx, cluster in enumerate(self._clusters):
            for term in cluster:
                self._term_cluster_map[term] = idx

        logger.info(
            "PMI clusters: %d clusters formed (largest=%d)",
            len(self._clusters),
            len(self._clusters[0]) if self._clusters else 0,
        )
        self._loaded = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()

    def __repr__(self) -> str:
        return f"PMIClustering(clusters={len(self._clusters)}, pairs={len(self._pmi_scores)})"
