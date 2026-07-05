"""Mathematical analysis modules for memory artifact scoring.

Provides corpus-level statistics (TF-IDF, BM25), entity graph analysis
(PageRank, centrality), TextRank (intra-session keyword graph), cross-turn
LSA and PMI, semantic similarity (embedding cosine), and a combined scorer
with configurable weights.

All modules are pure Python except semantic.py which depends on fastembed
and sqlite-vec from the project venv, and turn_analysis.py which optionally
uses numpy/scipy for faster SVD.
"""

# Inject project venv site-packages so fastembed, networkx, sqlite_vec
# are available regardless of which Python interpreter started the process.
from src._venv_inject import ensure_venv
ensure_venv()

from src.memory.analysis.corpus import MemoryCorpus, tokenize_doc, strip_code
from src.memory.analysis.graph_analysis import EntityGraph
from src.memory.analysis.pmi import PMIClustering
from src.memory.analysis.semantic import SemanticSimilarity
from src.memory.analysis.textrank import textrank_keywords, textrank_from_messages
from src.memory.analysis.turn_analysis import (
    LatentSemanticAnalysis,
    build_cross_turn_matrix,
    cross_pmi,
)
from src.memory.analysis.scoring import (
    CombinedScorer,
    DEFAULT_WEIGHTS,
    keyword_rank_with_scores,
    candidate_confidence_from_scores,
    compute_statistical_thresholds,
)

__all__ = [
    "MemoryCorpus",
    "tokenize_doc",
    "strip_code",
    "EntityGraph",
    "PMIClustering",
    "SemanticSimilarity",
    "textrank_keywords",
    "textrank_from_messages",
    "LatentSemanticAnalysis",
    "build_cross_turn_matrix",
    "cross_pmi",
    "CombinedScorer",
    "DEFAULT_WEIGHTS",
    "keyword_rank_with_scores",
    "candidate_confidence_from_scores",
    "compute_statistical_thresholds",
]
