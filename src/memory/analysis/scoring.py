"""Combined scoring, keyword ranking, candidate confidence, and statistical thresholds.

Formulas
--------
**Keyword combined score**::

    score(term) =
        w_bm25 * bm25(term, tf, doc_len)
      + w_tfidf * tfidf(term, tf)
      + w_centrality * entity_centrality(term)
      + w_pmi * pmi_cohesion(term)
      + w_semantic * semantic_sim(term)
      - w_freq_penalty * log(1 + df(term))

**Candidate confidence boost**::

    boost = w_keyword_boost * mean(keyword_scores)
          + w_entity_boost * max_entity_centrality
          + w_novelty_boost * (1 - max_semantic_similarity)

**Statistical thresholds** (for promotion decisions)::

    review_threshold     = mean + 1.0 * σ
    auto_promote_threshold = mean + 2.0 * σ
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from src.memory.analysis.corpus import MemoryCorpus
from src.memory.analysis.graph_analysis import EntityGraph
from src.memory.analysis.pmi import PMIClustering
from src.memory.analysis.semantic import SemanticSimilarity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default weights
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    # Keyword-level weights (sum ≈ 1.0)
    "bm25": 0.30,
    "tfidf": 0.08,
    "entity_centrality": 0.18,
    "pmi_cohesion": 0.08,
    "textrank": 0.12,          # intra-session graph importance
    "frequency_penalty": 0.10,  # novelty decay — penalises very common terms
    # Candidate confidence boost weights
    # Total boost sum ≈ 0.30 so max confidence ≈ 0.62 + 0.30 ≈ 0.92
    "candidate_keyword_boost": 0.10,
    "candidate_entity_boost": 0.05,
    "candidate_novelty_boost": 0.05,
    "candidate_centrality_boost": 0.03,
    "candidate_lsa_coherence": 0.04,  # cross-role topic alignment
    "candidate_cross_pmi": 0.03,      # user↔asst term pair strength
    # Threshold multipliers
    "review_sigma": 1.0,
    "auto_promote_sigma": 2.0,
    # Base confidence for candidates (fallback)
    "candidate_base": 0.60,
}


# ---------------------------------------------------------------------------
# CombinedScorer
# ---------------------------------------------------------------------------


class CombinedScorer:
    """Orchestrates corpus, graph, PMI, and semantic scoring.

    Parameters
    ----------
    corpus : MemoryCorpus | None
        Pre-built corpus stats. Created lazily if None.
    entity_graph : EntityGraph | None
        Pre-built entity graph. Created lazily if None.
    pmi : PMIClustering | None
        Pre-built PMI clustering. Created lazily if None.
    semantic : SemanticSimilarity | None
        Pre-built semantic similarity engine. Created lazily if None.
    weights : dict | None
        Weight overrides (merged with ``DEFAULT_WEIGHTS``).
    """

    def __init__(
        self,
        corpus: Optional[MemoryCorpus] = None,
        entity_graph: Optional[EntityGraph] = None,
        pmi: Optional[PMIClustering] = None,
        semantic: Optional[SemanticSimilarity] = None,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self._corpus = corpus
        self._entity_graph = entity_graph
        self._pmi = pmi
        self._semantic = semantic
        self._weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def set_weight(self, key: str, value: float) -> None:
        if key in self._weights:
            self._weights[key] = value
        else:
            logger.warning("Unknown weight key: %s", key)

    # ------------------------------------------------------------------
    # Keyword scoring
    # ------------------------------------------------------------------

    def score_keyword(
        self,
        term: str,
        tf: int,
        doc_len: int,
        textrank_score: float = 0.0,
    ) -> float:
        """Compute the combined score for a single keyword term.

        Uses BM25, TF-IDF, entity centrality, PMI cluster cohesion,
        TextRank (intra-session graph), and a frequency penalty.

        NOTE: Semantic similarity is NOT applied per-keyword — it is
        computed once at the session/candidate level in
        ``candidate_confidence``.

        Parameters
        ----------
        term : str
            The keyword (lowercased).
        tf : int
            Term frequency in the document.
        doc_len : int
            Document length (tokens).
        textrank_score : float
            Intra-session TextRank score (from ``textrank_keywords``) in [0, 1].
            Default 0.0 (no signal).

        Returns
        -------
        float
            Unnormalised combined score.
        """
        w = self._weights
        score = 0.0

        # BM25
        if self._corpus and w.get("bm25", 0) > 0:
            score += w["bm25"] * self._corpus.bm25(term, tf, doc_len)

        # TF-IDF
        if self._corpus and w.get("tfidf", 0) > 0:
            score += w["tfidf"] * self._corpus.tfidf(term, tf)

        # Entity centrality (PageRank) — if the keyword matches a known entity
        if self._entity_graph and w.get("entity_centrality", 0) > 0:
            score += w["entity_centrality"] * self._entity_graph.pagerank(term)

        # PMI cluster cohesion (how strongly this term clusters with others)
        if self._pmi and w.get("pmi_cohesion", 0) > 0:
            score += w["pmi_cohesion"] * self._pmi.cluster_cohesion(term)

        # TextRank — intra-session word-graph importance
        score += w.get("textrank", 0) * textrank_score

        # Frequency penalty (novelty decay) — penalise very common terms
        if self._corpus and w.get("frequency_penalty", 0) > 0:
            df = self._corpus.document_frequency(term)
            penalty = math.log(1 + df)
            score -= w["frequency_penalty"] * penalty

        return score

    def score_keywords_batch(
        self,
        term_tf_pairs: list[tuple[str, int]],
        doc_len: int,
        textrank_scores: Optional[dict[str, float]] = None,
    ) -> list[tuple[str, float]]:
        """Score a batch of (term, tf) pairs and return (term, score) sorted.

        Applies min-max normalisation across the batch so scores are in [0, 1].

        Parameters
        ----------
        term_tf_pairs : list[tuple[str, int]]
            (term, raw_frequency) pairs.
        doc_len : int
            Total token count in the document.
        textrank_scores : dict[str, float] | None
            Optional per-term TextRank scores from intra-session graph.
            Terms not present in the dict get 0.0.

        Returns
        -------
        list[tuple[str, float]]
            (term, normalised_score) sorted descending.
        """
        if not term_tf_pairs:
            return []

        tr = textrank_scores or {}
        raw = [
            (term, self.score_keyword(term, tf, doc_len, textrank_score=tr.get(term, 0.0)))
            for term, tf in term_tf_pairs
        ]

        # Min-max normalise
        scores = [s for _, s in raw]
        lo, hi = min(scores), max(scores)
        if hi - lo > 1e-9:
            normalised = [(term, (s - lo) / (hi - lo)) for term, s in raw]
        else:
            normalised = [(term, 0.5) for term, _ in raw]

        return sorted(normalised, key=lambda x: (-x[1], x[0]))

    # ------------------------------------------------------------------
    # Candidate confidence
    # ------------------------------------------------------------------

    def candidate_confidence(
        self,
        keyword_scores: list[tuple[str, float]],
        entity_names: list[str],
        session_text: str = "",
        base_confidence: float = 0.60,
        lsa_coherence: float = 0.0,
        lsa_reliability: float = 0.0,
        cross_pmi_score: float = 0.0,
        pmi_reliability: float = 0.0,
    ) -> float:
        """Compute an enhanced candidate confidence score.

        Incorporates keyword significance, entity centrality, semantic novelty,
        keyword-level entity overlap, LSA cross-role coherence, and cross-turn
        PMI (user↔assistant term pairs).

        **Adaptive weighting**: The ``lsa_coherence`` and ``cross_pmi_score``
        contributions are scaled by their respective ``*_reliability`` factors
        (algebraically derived from signal-to-noise ratio per session). When a
        metric has no data (reliability=0), its weight drops to zero
        automatically.

        Parameters
        ----------
        keyword_scores : list[tuple[str, float]]
            Ranked (term, score) pairs from ``score_keywords_batch``.
        entity_names : list[str]
            Entity names detected in the session.
        session_text : str
            Full session text for semantic comparison (only used if
            ``semantic_similarity`` engine is available).
        base_confidence : float
            Fallback confidence from signal-word analysis.
        lsa_coherence : float
            Mean cosine similarity between consecutive user↔assistant turn
            topic vectors (from LSA).  Values in [0, 1]; high = coherent
            conversation.
        lsa_reliability : float
            Algebraic reliability of LSA in [0, 1].  Derived from number of
            user turns: ``min(1.0, n_user_turns / 5)``.  Scales the
            LSA weight adaptively.
        cross_pmi_score : float
            Mean PMI of top user↔assistant term pairs.  Values in [0, 1]
            after sigmoid normalisation; high = strong cross-role term
            linking.
        pmi_reliability : float
            Algebraic reliability of cross-PMI in [0, 1].  Derived from
            number of co-occurring term pairs: ``min(1.0, n_pairs / 10)``.
            Scales the PMI weight adaptively.

        Returns
        -------
        float
            Confidence in [0, 1].
        """
        w = self._weights

        # Keyword boost: mean of top-5 keyword scores
        top5 = keyword_scores[:5]
        kw_boost = sum(s for _, s in top5) / max(len(top5), 1) if top5 else 0.0

        # Entity boost: max PageRank among explicitly detected entities
        ent_boost = 0.0
        if self._entity_graph and entity_names:
            ent_boost = self._entity_graph.max_centrality_for_any(entity_names)

        # Novelty boost: (1 - max_semantic_similarity) — low sim = high novelty
        novelty = 0.0
        if self._semantic and session_text and self._semantic.enabled:
            sim = self._semantic.max_similarity(session_text[:2048])
            novelty = 1.0 - sim

        # Centrality of TOP keywords themselves (implicit entity overlap)
        kw_centrality_boost = 0.0
        if self._entity_graph and keyword_scores:
            top_kw_terms = [t for t, _ in keyword_scores[:3]]
            kw_centrality_boost = self._entity_graph.max_centrality_for_any(
                top_kw_terms
            )

        # Adaptive boosts: weights are scaled by signal reliability
        # When a metric has no data, its effective contribution drops to 0
        lsa_boost = (
            w.get("candidate_lsa_coherence", 0.04) * lsa_reliability * lsa_coherence
        )
        pmi_boost = (
            w.get("candidate_cross_pmi", 0.03) * pmi_reliability * cross_pmi_score
        )

        combined = (
            base_confidence
            + w.get("candidate_keyword_boost", 0.10) * kw_boost
            + w.get("candidate_entity_boost", 0.05) * ent_boost
            + w.get("candidate_novelty_boost", 0.05) * novelty
            + w.get("candidate_centrality_boost", 0.03) * kw_centrality_boost
            + lsa_boost
            + pmi_boost
        )

        # Clamp to [0, 1]
        return max(0.0, min(1.0, combined))


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def keyword_rank_with_scores(
    term_counts: dict[str, int],
    doc_len: int,
    scorer: CombinedScorer,
) -> list[tuple[str, float]]:
    """Rank (term → raw count) against corpus and return scored + sorted.

    Parameters
    ----------
    term_counts : dict[str, int]
        Raw term frequencies from the session.
    doc_len : int
        Total token count for the session.
    scorer : CombinedScorer
        Pre-configured scorer with corpus, graph, etc.

    Returns
    -------
    list[tuple[str, float]]
        Sorted (term, normalised_score) descending.
    """
    pairs = list(term_counts.items())
    return scorer.score_keywords_batch(pairs, doc_len)


def candidate_confidence_from_scores(
    keyword_scores: list[tuple[str, float]],
    entity_names: list[str],
    session_text: str,
    scorer: CombinedScorer,
    base_confidence: float = 0.60,
    lsa_coherence: float = 0.0,
    lsa_reliability: float = 0.0,
    cross_pmi_score: float = 0.0,
    pmi_reliability: float = 0.0,
) -> float:
    """Wraps ``CombinedScorer.candidate_confidence``."""
    return scorer.candidate_confidence(
        keyword_scores,
        entity_names,
        session_text=session_text,
        base_confidence=base_confidence,
        lsa_coherence=lsa_coherence,
        lsa_reliability=lsa_reliability,
        cross_pmi_score=cross_pmi_score,
        pmi_reliability=pmi_reliability,
    )


# ---------------------------------------------------------------------------
# Statistical thresholds
# ---------------------------------------------------------------------------


def compute_statistical_thresholds(
    scores: list[float],
    review_sigma: float = 1.0,
    auto_promote_sigma: float = 2.0,
) -> dict[str, float]:
    """Compute mean, std, and promotion thresholds from a list of scores.

    Parameters
    ----------
    scores : list[float]
        Confidence scores across candidates.
    review_sigma : float
        Number of standard deviations above mean for review threshold.
    auto_promote_sigma : float
        Number of standard deviations above mean for auto-promote.

    Returns
    -------
    dict with keys: ``mean``, ``std``, ``min``, ``max``, ``review_threshold``,
    ``auto_promote_threshold``, ``n``.
    """
    n = len(scores)
    if n == 0:
        return {
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "review_threshold": 0.0,
            "auto_promote_threshold": 0.0,
            "n": 0,
        }

    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / max(n - 1, 1)
    std = math.sqrt(variance)

    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": round(min(scores), 4),
        "max": round(max(scores), 4),
        "review_threshold": round(mean + review_sigma * std, 4),
        "auto_promote_threshold": round(mean + auto_promote_sigma * std, 4),
        "n": n,
    }
