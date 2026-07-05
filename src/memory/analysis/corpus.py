"""Corpus-level statistics for memory artifact scoring.

Computes:
  - Document frequency (DF): number of documents a term appears in
  - Total document count (N)
  - Average document length (avgdl) for BM25 length normalisation
  - Inverse document frequency (IDF) with smoothing
  - BM25 and TF-IDF scoring functions
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared stopword / noise token list
# ---------------------------------------------------------------------------
STOP = {
    # Spanish common stopwords
    "para", "pero", "como", "todo", "esta", "este", "esto", "tiene",
    "sobre", "cuando", "porque", "entonces", "donde", "sino", "cada",
    "tambien", "despues", "antes", "nunca", "siempre", "ahora", "aqui",
    "alla", "alli", "hacia", "hasta", "media", "medio", "misma", "mismo",
    "unas", "unos", "otra", "otro", "otras", "otros", "esos", "esas",
    "estos", "estas", "aquel", "aquella", "seria", "podria", "puede",
    "debe", "tanto", "vamos", "vaya", "hecho", "dice", "dijo", "hace",
    "poco", "mucha", "mucho", "todas", "todos", "cual", "cuales",
    "entre", "contra", "segun", "durante", "mediante", "solo", "sola",
    "bueno", "buena", "gran", "nueva", "nuevo", "nuevas", "nuevos",
    "estoy", "estas", "esta", "estamos", "estan", "eres", "soy",
    "eres", "somos", "sois", "son", "seas", "sea", "seamos", "sean",
    "fuera", "fueras", "fuera", "fueramos", "fueran",
    "sido", "siendo",
    # Accented variants of Spanish stopwords
    "está", "están", "más",
    # High-frequency Spanish filler words with low semantic signal
    "cosas", "hacer", "hola", "bien", "dias", "dia", "nada", "algo",
    "ademas", "algunas", "algunos", "bastante", "grande", "saber",
    "tema", "luego", "mira", "hice", "queria", "tengo", "haciendo",
    "aunque", "asi", "siempre", "nunca", "siendo", "hecho",
    "noche", "tarde", "temprano", "rato",
    "años", "año", "dia", "dias", "final", "sentido",
    "desde", "buscar", "cualquier", "cualquiera",
    "mañana", "tarde", "noche", "semana", "mes", "años",
    "consciente", "pensando", "puedo", "puedes", "puede",
    "propia", "propio", "propias", "propios",
    "parte", "partes", "tipo", "tipos", "forma", "formas",
    "lado", "lados", "vez", "veces", "modo", "manera",
    # English common stopwords
    "then", "with", "that", "this", "from", "what", "which", "where",
    "when", "than", "been", "have", "they", "them", "these", "those",
    "would", "could", "should", "about", "there", "their", "your",
    "some", "such", "also", "very", "just", "only", "more", "most",
    "much", "many", "each", "well", "here", "will", "into",
    "done", "need", "look", "know", "like", "want", "get", "put",
    "may", "might", "must", "shall", "can", "ought",
    "every", "both", "few", "several", "own", "same", "other",
    "any", "all", "both",
    # Metadata / structural tokens that leak from artifact text
    "session", "sessions", "message", "messages", "content",
    "channel", "keyword", "keywords", "metadata", "snapshot",
    "assistant", "extractive", "available",
    "user_message_count", "assistant_message_count",
    "notes", "source", "sources",
    "first", "last",
    # English noise tokens that leak from system/error messages
    # (common in retry loops, injected context, copy-pasted logs)
    "model", "system", "encountered", "please", "previous", "prior",
    "again", "same",
    # Infrastructure / framework tokens (NOT conversational)
    "tools", "tool", "commit", "commits", "backup", "clipboard",
    "sseclient", "sessionstore", "handler", "to_thread", "sync",
    "selector", "failover", "rebuild", "migrate", "migration",
    # CSS / frontend tokens that leak from widget conversations
    "span", "font", "margin", "fill", "stroke", "width", "circle",
    "state", "style", "document", "border", "textcontent", "color",
    "drag", "drop", "click", "hover", "scroll", "event", "target",
    "background", "height", "left", "right", "top", "bottom",
    "inline", "block", "flex", "grid", "solid", "dashed", "dotted",
    "opacity", "shadow", "radius", "padding",
    # Code / debug tokens (meaningless for conversational memory)
    "none", "import", "_deps", "self", "return", "logger", "config",
    "async", "await", "true", "false", "class", "function", "const",
    "var", "let", "def", "type", "null", "undefined", "lambda",
    "raise", "except", "finally", "yield", "global", "nonlocal",
    "print", "len", "str", "int", "dict", "list", "tuple", "set",
    "range", "enumerate", "zip", "map", "filter", "sorted",
    "property", "staticmethod", "classmethod", "super", "object",
    "value", "values", "items", "keys", "key", "node", "expected",
    "assert", "match", "case", "break", "continue", "pass", "del",
    "exec", "eval", "input", "open", "file", "try", "except", "finally",
    "else", "elif", "if", "and", "or", "not", "is", "in", "as", "with",
    "any", "all", "both", "call", "name", "main", "test", "tests",
    "param", "params", "args", "kwargs", "path", "paths",
    "data", "text", "show", "make",
    "maybe", "always", "never", "already", "still", "even", "though",
    "attempt", "retry", "error", "failed", "failure", "exception",
    "timeout", "status", "exists", "assume", "assumed", "assumption",
    "connection", "connect", "connected", "connecting",
    "response", "request", "header", "headers", "payload",
    "server", "client", "protocol", "schema", "endpoint",
    "config", "configure", "configuration", "setting", "settings",
    "string", "integer", "boolean", "array", "object",
    "method", "function", "attribute", "property",
    "using", "used", "uses", "use",
    "going", "goes", "went", "gone",
    "saying", "said", "says", "say",
    "making", "makes", "made",
    "taking", "takes", "took", "taken",
    "giving", "gives", "gave", "given",
    "coming", "comes", "came", "come",
    "seeing", "sees", "saw", "seen",
    "thinking", "thinks", "thought", "think",
    "putting", "puts",
    "letting", "lets", "let",
    "setting", "sets",
    "running", "runs", "ran", "run",
    "working", "works", "worked",
    "trying", "tries", "tried",
    "calling", "calls", "called",
    "asking", "asks", "asked",
    "talking", "talks", "talked",
    "wants", "wanted",
    "needs", "needed",
    "looks", "looked",
    "seems", "seemed",
    "helps", "helped",
    "starts", "started",
    "keeps", "kept",
    "means", "meant",
    "feels", "felt",
    "finds", "found",
    "brings", "brought",
    "plays", "played",
    "follow", "follows", "followed",
    "supports", "supported",
    "includes", "included",
    "contains", "contained",
    "removes", "removed",
    "creates", "created",
    "updates", "updated",
    "handles", "handled",
    "returns", "returned",
    "manages", "managed",
}

# ---------------------------------------------------------------------------
# Code block stripping (prevents code from inflating LSA vocabulary)
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")


def strip_code(text: str) -> str:
    """Remove markdown code blocks and inline code from text.

    This prevents Python/JS/CSS code from inflating the vocabulary
    when computing LSA or keyword scores, which was causing false
    negatives in code-heavy sessions.
    """
    cleaned = _CODE_BLOCK_RE.sub(" ", text)
    cleaned = _INLINE_CODE_RE.sub(" ", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def tokenize_doc(text: str, *, strip_code_blocks: bool = False) -> list[str]:
    """Tokenize and normalize artifact text, returning meaningful terms.

    Strips stopwords, code tokens, UUID-like strings, timestamps,
    and single-character tokens.

    Parameters
    ----------
    text : str
        Raw text to tokenize.
    strip_code_blocks : bool
        If True, remove markdown code blocks (triple backticks) and
        inline code before tokenization.  Use this for conversation
        analysis to prevent code from fragmenting the semantic space.
    """
    if strip_code_blocks:
        text = strip_code(text)

    tokens: list[str] = []
    for raw in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]{4,}", text or ""):
        token = raw.lower().strip("._-")
        if not token:
            continue
        if token in STOP:
            continue
        if token.isdigit():
            continue
        if re.fullmatch(r"[a-f0-9]{12,}", token):
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}t?\d*", token):
            continue
        if re.fullmatch(r"[a-f0-9-]{20,}", token):
            continue
        tokens.append(token)
    return tokens


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


class MemoryCorpus:
    """Collection-level statistics computed across session summary artifacts.

    Attributes
    ----------
    N : int
        Number of documents (session summaries) in the corpus.
    avgdl : float
        Average document length (in tokens) across the corpus.
    df : dict[str, int]
        Document frequency — how many documents each term appears in.
    """

    def __init__(self, artifacts_root: str | Path) -> None:
        self._root = Path(artifacts_root)
        self._df: dict[str, int] = {}
        self._N: int = 0
        self._avgdl: float = 0.0
        self._loaded = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def N(self) -> int:
        self._ensure_loaded()
        return self._N

    @property
    def avgdl(self) -> float:
        self._ensure_loaded()
        return self._avgdl

    @property
    def df(self) -> dict[str, int]:
        self._ensure_loaded()
        return dict(self._df)

    def document_frequency(self, term: str) -> int:
        """Return how many documents contain *term* (0 if unseen)."""
        self._ensure_loaded()
        return self._df.get(term, 0)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Scan ``memory/*/*/*/session--*.md`` and recompute stats."""
        logger.info("Refreshing corpus stats from session summary artifacts …")
        df_acc: dict[str, set[str]] = defaultdict(set)
        total_tokens = 0
        doc_count = 0

        for path in sorted(self._root.glob("memory/*/*/*/session--*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Cannot read %s: %s", path, exc)
                continue
            tokens = tokenize_doc(text)
            unique = set(tokens)
            for term in unique:
                df_acc[term].add(path.stem)
            total_tokens += len(tokens)
            doc_count += 1

        self._df = {term: len(sessions) for term, sessions in df_acc.items()}
        self._N = doc_count
        self._avgdl = total_tokens / max(doc_count, 1)
        self._loaded = True

        logger.info(
            "Corpus refreshed: N=%d, avgdl=%.1f, vocabulary=%d",
            self._N,
            self._avgdl,
            len(self._df),
        )

    # ------------------------------------------------------------------
    # IDF
    # ------------------------------------------------------------------

    def idf(self, term: str) -> float:
        """Smoothed inverse document frequency.

        ``idf = log((N + 1) / (df + 1)) + 1``
        """
        self._ensure_loaded()
        df = self._df.get(term, 0)
        return math.log((self._N + 1) / (df + 1)) + 1.0

    # ------------------------------------------------------------------
    # BM25
    # ------------------------------------------------------------------

    def bm25(
        self,
        term: str,
        tf: int,
        doc_len: int,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """BM25 score for a single term in a document.

        Parameters
        ----------
        term : str
            The query term.
        tf : int
            Term frequency in the document.
        doc_len : int
            Length (in tokens) of the document.
        k1 : float
            Term-frequency saturation parameter (1.2–2.0).
        b : float
            Length-normalisation parameter (0.0–1.0).
        """
        self._ensure_loaded()

        if self._N == 0:
            return 0.0  # no corpus — no meaningful score

        df = self._df.get(term, 0)
        idf_bm25 = math.log((self._N - df + 0.5) / (df + 0.5) + 1.0)

        # Guard against empty corpus (avgdl == 0)
        if self._avgdl <= 0:
            length_norm = 1.0
        else:
            length_norm = 1 - b + b * doc_len / self._avgdl

        tf_saturated = (tf * (k1 + 1)) / (tf + k1 * length_norm)
        return idf_bm25 * tf_saturated

    # ------------------------------------------------------------------
    # TF-IDF (standard, convenient for comparison)
    # ------------------------------------------------------------------

    def tfidf(self, term: str, tf: int) -> float:
        """Convenience wrapper: ``tf * idf``."""
        return tf * self.idf(term)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()

    def __repr__(self) -> str:
        return (
            f"MemoryCorpus(N={self._N}, avgdl={self._avgdl:.1f}, "
            f"vocab={len(self._df) if self._loaded else '?'})"
        )
