"""TextRank — unsupervised graph-based keyword extraction for a single document.

TextRank treats each unique word as a node in a graph.  Edges are created
when two words co-occur within a sliding window of *w* tokens.  PageRank
is then run over this graph; the highest-ranked nodes are the most
important keywords *for this specific document*.

This is complementary to BM25: BM25 scores against the corpus (global),
while TextRank scores within the document (local).  Combining both gives
a term that is both distinctive in the session AND central within it.

Reference
---------
Mihalcea & Tarau (2004).  TextRank: Bringing Order into Text.
https://aclanthology.org/W04-3252/
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TextRank
# ---------------------------------------------------------------------------


def textrank_keywords(
    tokens: list[str],
    *,
    window: int = 5,
    damping: float = 0.85,
    max_iter: int = 100,
    tol: float = 1e-6,
    limit: int = 15,
) -> list[tuple[str, float]]:
    """Run TextRank over a tokenised document and return ranked keywords.

    Parameters
    ----------
    tokens : list[str]
        Normalised tokens from a single document (session text).
    window : int
        Co-occurrence window size (sliding).  Default 5.
    damping : float
        PageRank damping factor.  Default 0.85.
    max_iter : int
        Maximum PageRank iterations.  Default 100.
    tol : float
        Convergence tolerance.  Default 1e-6.
    limit : int
        Max keywords to return.  Default 15.

    Returns
    -------
    list[tuple[str, float]]
        ``(term, textrank_score)`` sorted descending by score.

    Notes
    -----
    - Tokens appearing fewer than 2 times are excluded (no graph utility).
    - Scores are min-max normalised to [0, 1].
    """
    if len(tokens) < window:
        return []

    # 1. Count frequencies and build vocab
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1

    # Keep only tokens with at least 2 occurrences (they contribute edges)
    vocab = {t for t, c in freq.items() if c >= 2}
    if len(vocab) < 3:
        return []

    # 2. Build co-occurrence graph
    #    Edge weight = number of times two words co-occur within *window*
    adj: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for i in range(len(tokens)):
        if tokens[i] not in vocab:
            continue
        for j in range(i + 1, min(i + window, len(tokens))):
            if tokens[j] not in vocab:
                continue
            if tokens[i] != tokens[j]:
                adj[tokens[i]][tokens[j]] += 1.0
                adj[tokens[j]][tokens[i]] += 1.0

    if not adj:
        return []

    # 3. PageRank on the word graph
    n = len(adj)
    pr: dict[str, float] = {node: 1.0 / n for node in adj}

    for _ in range(max_iter):
        new_pr: dict[str, float] = {}
        for node in adj:
            score = 0.0
            for neighbor in adj[node]:
                out_degree = max(sum(adj[neighbor].values()), 1)
                score += pr[neighbor] * adj[neighbor][node] / out_degree
            new_pr[node] = (1 - damping) / n + damping * score

        diff = sum(abs(new_pr[node] - pr[node]) for node in pr)
        pr = new_pr
        if diff < tol:
            break

    # 4. Rank and normalise
    ranked = sorted(pr.items(), key=lambda x: (-x[1], x[0]))
    scores = [s for _, s in ranked]
    lo, hi = min(scores), max(scores)
    if hi - lo > 1e-9:
        normalised = [(term, (s - lo) / (hi - lo)) for term, s in ranked]
    else:
        normalised = [(term, 0.5) for term, _ in ranked]

    return normalised[:limit]


# ---------------------------------------------------------------------------
# Convenience: run TextRank on raw message text
# ---------------------------------------------------------------------------


def textrank_from_messages(
    messages: list[dict],
    *,
    include_roles: tuple[str, ...] = ("user", "assistant"),
    window: int = 5,
    limit: int = 15,
) -> list[tuple[str, float]]:
    """Tokenise messages and run TextRank over the combined text.

    Parameters
    ----------
    messages : list[dict]
        Messages with ``role`` and ``content`` keys.
    include_roles : tuple[str, ...]
        Which roles to include (default both user and assistant).
    window : int
        TextRank co-occurrence window.
    limit : int
        Max keywords to return.

    Returns
    -------
    list[tuple[str, float]]
        Ranked (term, score) pairs.
    """
    from src.memory.analysis.corpus import tokenize_doc

    combined_tokens: list[str] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        if role not in include_roles:
            continue
        content = str(msg.get("content") or "")
        if content.startswith("[SYSTEM:"):
            continue
        combined_tokens.extend(tokenize_doc(content))

    if not combined_tokens:
        return []

    return textrank_keywords(combined_tokens, window=window, limit=limit)
