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

# Keep this package import light. Import analysis submodules directly from the
# call sites that need them so simple imports do not pull in heavyweight deps.

__all__: list[str] = []
