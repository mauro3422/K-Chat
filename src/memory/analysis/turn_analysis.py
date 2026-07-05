"""Cross-turn analysis — user↔assistant term linking and LSA.

Provides two complementary algebraic views of conversation structure:

1. **Cross-turn PMI matrix** — builds a bipartite co-occurrence matrix
   between user terms and assistant terms (across consecutive turns),
   then computes PMI to find strongly associated cross-role pairs.

2. **LSA (Latent Semantic Analysis)** — builds a turn×term TF-IDF matrix,
   applies truncated SVD, and returns per-turn topic vectors.  Use the
   cosine between user-turn and assistant-turn topic vectors to measure
   conversational coherence (``linkear párrafos por álgebra``).

All matrices are pure Python (no numpy/scipy dependency) using lists of
dicts, keeping it runnable in the system Python if needed.  For large
conversations a numpy-backed version can be swapped in later.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from typing import Any, Optional

from src.memory.analysis.corpus import tokenize_doc

logger = logging.getLogger(__name__)

# ======================================================================
# 1. Cross-turn PMI
# ======================================================================


def build_cross_turn_matrix(
    messages: list[dict[str, Any]],
    window: int = 1,
) -> dict[str, dict[str, float]]:
    """Build a bipartite user→assistant term co-occurrence matrix.

    For each consecutive (user → assistant) turn pair, all terms from the
    user message are paired with all terms from the assistant response.
    The result is a nested dict::

        matrix[user_term][asst_term] = raw_co_occurrence_count

    Parameters
    ----------
    messages : list[dict]
        Chronological messages with ``role`` and ``content`` keys.
    window : int
        How many turns ahead to look for the paired response (default 1).

    Returns
    -------
    dict[str, dict[str, float]]
        ``{user_term: {asst_term: count}}``.
    """
    # Collect (role, tokens) for each message
    turns: list[tuple[str, list[str]]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        content = str(msg.get("content") or "")
        if content.startswith("[SYSTEM:"):
            continue
        tokens = tokenize_doc(content, strip_code_blocks=True)
        if tokens:
            turns.append((role, tokens))

    matrix: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    # Scan consecutive (user → assistant) pairs
    for i in range(len(turns) - 1):
        role_i, toks_i = turns[i]
        for j in range(i + 1, min(i + 1 + window, len(turns))):
            role_j, toks_j = turns[j]
            if role_i == "user" and role_j == "assistant":
                for ut in toks_i:
                    for at in toks_j:
                        if ut != at:  # skip same-term (trivial co-occurrence)
                            matrix[ut][at] += 1.0

    # Convert back to plain dict
    return {str(u): dict(a) for u, a in matrix.items()}


def cross_pmi(
    matrix: dict[str, dict[str, float]],
    min_cooc: int = 2,
) -> dict[tuple[str, str], float]:
    """Compute PMI on a cross-turn co-occurrence matrix.

    PMI(user_term, asst_term) = log( P(u,a) / (P(u) · P(a)) )

    Parameters
    ----------
    matrix : dict
        Output of ``build_cross_turn_matrix``.
    min_cooc : int
        Minimum raw co-occurrence count to consider.

    Returns
    -------
    dict[tuple[str, str], float]
        ``{(user_term, asst_term): pmi_score}``, filtered by *min_cooc*.
    """
    # Flatten to collect totals
    total = 0.0
    u_marg: dict[str, float] = defaultdict(float)
    a_marg: dict[str, float] = defaultdict(float)
    cooc: dict[tuple[str, str], float] = {}

    for u_term, asst_dict in matrix.items():
        for a_term, count in asst_dict.items():
            if count < min_cooc:
                continue
            total += count
            u_marg[u_term] += count
            a_marg[a_term] += count
            cooc[(u_term, a_term)] = count

    if total < 1:
        return {}

    # PMI
    pmi_scores: dict[tuple[str, str], float] = {}
    for (u_term, a_term), count in cooc.items():
        p_ua = count / total
        p_u = u_marg[u_term] / total
        p_a = a_marg[a_term] / total
        if p_u > 0 and p_a > 0 and p_ua > 0:
            pmi = math.log(p_ua / (p_u * p_a))
            pmi_scores[(u_term, a_term)] = round(pmi, 4)

    return pmi_scores


# ======================================================================
# 2. LSA (Latent Semantic Analysis) via truncated SVD
# ======================================================================


class LatentSemanticAnalysis:
    """Truncated SVD over a turn×term TF-IDF matrix.

    Finds latent "topics" that explain the conversation structure.  Each
    turn gets a topic-distribution vector; turns with similar vectors are
    semantically related even if they use different words.

    Parameters
    ----------
    n_topics : int
        Number of latent topics (k for truncated SVD).  Default 5.
    n_iter : int
        Power-method iterations for approximate SVD.  Default 10.
    """

    def __init__(self, n_topics: int = 5, n_iter: int = 10) -> None:
        self.n_topics = n_topics
        self.n_iter = n_iter
        # Results populated by ``fit``
        self.turn_labels: list[str] = []          # per-turn: "(user|asst):idx"
        self.topic_vectors: list[list[float]] = []  # per-turn: topic distribution
        self.term_loadings: dict[str, list[float]] = {}  # per-term: loading per topic
        self.singular_values: list[float] = []
        self.vocab: list[str] = []
        # Metadata for adaptive weighting
        self.n_user_turns: int = 0
        self.n_asst_turns: int = 0

    def fit(self, messages: list[dict[str, Any]]) -> "LatentSemanticAnalysis":
        """Build the turn×term matrix and run truncated SVD.

        Parameters
        ----------
        messages : list[dict]
            Chronological messages with ``role`` and ``content`` keys.
        """
        # --- 1. Collect turns and vocab ---
        turns: list[tuple[str, list[str]]] = []
        term_doc_freq: Counter[str] = Counter()
        term_total_freq: Counter[str] = Counter()

        for idx, msg in enumerate(messages):
            role = str(msg.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            content = str(msg.get("content") or "")
            if content.startswith("[SYSTEM:"):
                continue
            # Strip code blocks to prevent code from inflating LSA vocabulary
            tokens = tokenize_doc(content, strip_code_blocks=True)
            if not tokens:
                continue
            unique = set(tokens)
            term_doc_freq.update(unique)  # document frequency (for IDF)
            term_total_freq.update(tokens)
            turns.append((role, tokens))
            if role == "user":
                self.n_user_turns += 1
            else:
                self.n_asst_turns += 1

        if not turns:
            return self

        self.vocab = sorted(term_total_freq.keys())
        vocab_idx = {t: i for i, t in enumerate(self.vocab)}
        V = len(self.vocab)
        T = len(turns)
        N = max(T, 1)

        # --- 2. Build TF-IDF matrix as list of sparse dicts ---
        # Each turn → {term_idx: tfidf}
        tfidf_turns: list[dict[int, float]] = []

        for role, tokens in turns:
            tf = Counter(tokens)
            vec: dict[int, float] = {}
            for term, freq in tf.items():
                idx = vocab_idx.get(term)
                if idx is None:
                    continue
                df = term_doc_freq.get(term, 1)
                idf = math.log((N + 1) / (df + 1)) + 1.0
                vec[idx] = freq * idf
            tfidf_turns.append(vec)

        self.turn_labels = [f"{r}:{i}" for i, (r, _) in enumerate(turns)]

        # --- 3. Truncated SVD via power iteration ---
        # X ≈ U · Σ · V^T
        # X = [T × V] (turns × terms)
        # We want: U = [T × k], V = [V × k], Σ = [k]
        k = min(self.n_topics, T, V)
        if k < 1:
            return self

        # Initial random V (terms × topics)
        import random as _random
        rng = _random.Random(42)
        V_hat = [[rng.gauss(0, 1) for _ in range(k)] for _ in range(V)]

        # Power iteration: X^T · X · V = V · Σ²
        for iteration in range(self.n_iter):
            # Y = X · V_hat  [T × k]
            Y = [[0.0] * k for _ in range(T)]
            for t_idx, t_vec in enumerate(tfidf_turns):
                for term_idx, val in t_vec.items():
                    for topic in range(k):
                        Y[t_idx][topic] += val * V_hat[term_idx][topic]

            # Z = X^T · Y  [V × k]
            Z = [[0.0] * k for _ in range(V)]
            for t_idx, t_vec in enumerate(tfidf_turns):
                for term_idx, val in t_vec.items():
                    for topic in range(k):
                        Z[term_idx][topic] += val * Y[t_idx][topic]

            # QR-like normalisation via Gram-Schmidt on Z columns
            for topic in range(k):
                # Normalise
                norm = math.sqrt(sum(Z[row][topic] ** 2 for row in range(V)))
                if norm > 1e-12:
                    for row in range(V):
                        Z[row][topic] /= norm
                # Orthogonalise against previous topics
                for prev in range(topic):
                    dot = sum(Z[row][topic] * Z[row][prev] for row in range(V))
                    for row in range(V):
                        Z[row][topic] -= dot * Z[row][prev]
                # Re-normalise after orthogonalisation
                norm = math.sqrt(sum(Z[row][topic] ** 2 for row in range(V)))
                if norm > 1e-12:
                    for row in range(V):
                        Z[row][topic] /= norm

            V_hat = Z

        # V_hat = right singular vectors [V × k]
        # Compute singular values: σ_i = ||X · V_hat[:, i]||
        sv: list[float] = []
        for topic in range(k):
            # Y = X · V_hat[:, topic]
            y_norm_sq = 0.0
            for t_idx, t_vec in enumerate(tfidf_turns):
                dot = sum(t_vec.get(term_idx, 0.0) * V_hat[term_idx][topic]
                          for term_idx in range(V))
                y_norm_sq += dot * dot
            sv.append(math.sqrt(y_norm_sq))

        self.singular_values = [round(s, 4) for s in sv]

        # Compute U = X · V · Σ^{-1}
        U: list[list[float]] = [[0.0] * k for _ in range(T)]
        for t_idx, t_vec in enumerate(tfidf_turns):
            for topic in range(k):
                if sv[topic] > 1e-12:
                    dot = sum(t_vec.get(term_idx, 0.0) * V_hat[term_idx][topic]
                              for term_idx in range(V))
                    U[t_idx][topic] = round(dot / sv[topic], 4)

        # Normalise U rows to unit length (topic distribution per turn)
        for t_idx in range(T):
            norm = math.sqrt(sum(U[t_idx][topic] ** 2 for topic in range(k)))
            if norm > 1e-12:
                for topic in range(k):
                    U[t_idx][topic] /= norm

        self.topic_vectors = U

        # Term loadings = V_hat (each row is a term's loading per topic)
        self.term_loadings = {}
        for term, idx in vocab_idx.items():
            if idx < V:
                self.term_loadings[term] = [round(V_hat[idx][t], 4) for t in range(k)]

        logger.info(
            "LSA: %d turns × %d terms → %d topics (σ=%s)",
            T, V, k, self.singular_values[:4],
        )
        return self

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def turn_similarity(self, turn_i: int, turn_j: int) -> float:
        """Cosine similarity between two turns' topic vectors."""
        if not self.topic_vectors:
            return 0.0
        if turn_i >= len(self.topic_vectors) or turn_j >= len(self.topic_vectors):
            return 0.0
        vi = self.topic_vectors[turn_i]
        vj = self.topic_vectors[turn_j]
        dot = sum(vi[t] * vj[t] for t in range(len(vi)))
        return round(dot, 4)

    def cross_role_similarities(
        self,
    ) -> list[tuple[int, int, float]]:
        """Return all (user_turn_idx, asst_turn_idx, cosine) pairs.

        Only consecutive (user → assistant) pairs are considered.
        """
        result: list[tuple[int, int, float]] = []
        for i in range(len(self.turn_labels) - 1):
            if self.turn_labels[i].startswith("user") and self.turn_labels[i + 1].startswith("assist"):
                sim = self.turn_similarity(i, i + 1)
                result.append((i, i + 1, sim))
        return result

    def dominant_topic_per_turn(self) -> list[tuple[str, int, float]]:
        """For each turn, return ``(label, dominant_topic, weight)``."""
        out: list[tuple[str, int, float]] = []
        for idx, label in enumerate(self.turn_labels):
            if idx < len(self.topic_vectors):
                vec = self.topic_vectors[idx]
                dom_topic = max(range(len(vec)), key=lambda t: vec[t])
                out.append((label, dom_topic, round(vec[dom_topic], 4)))
        return out
