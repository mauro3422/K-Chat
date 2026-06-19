"""TF-IDF keyword extractor in pure Python (no sklearn).

Extracts the most representative keywords from text using
Term Frequency - Inverse Document Frequency scoring.

Usage:
    from src.memory.keywords.extractor import extract_keywords
    keywords = extract_keywords("texto del exchange aqui")
    # Returns: [("async", 0.45), ("tools", 0.32), ("audit", 0.28)]
"""

import logging
import math
import re
import threading
from contextvars import ContextVar
from collections import Counter
from typing import Optional

# ── Bilingual stopword list (Spanish + English) ─────────────────────
_STOPWORDS: set[str] = {
    # Spanish
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se",
    "las", "por", "un", "para", "con", "no", "una", "su", "al", "lo",
    "como", "más", "pero", "sus", "le", "ya", "este", "entre", "porque",
    "ese", "eso", "esa", "eso", "todo", "esta", "este", "muy", "sin",
    "hay", "ahora", "aquí", "allí", "bien", "ser", "estar", "haber",
    "tener", "hacer", "sido", "siendo", "vez", "dos", "poco", "era",
    "tan", "cada", "solo", "también", "después", "así", "así", "cómo",
    "qué", "quién", "cuándo", "dónde", "cual", "cuanto", "tan", "tanto",
    "nada", "algo", "alguien", "nadie", "si", "no", "también", "sino",
    "fue", "fui", "eras", "fuera", "fuese", "sea", "sido", "está",
    "estoy", "estamos", "están", "estaba", "estaban", "estado",
    "tu", "tus", "te", "ti", "mi", "mis", "nos", "os", "les", "sus",
    "ello", "ellos", "ellas", "nosotros", "vosotros", "usted", "ustedes",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "aquel", "aquella", "aquellos", "aquellas",
    "van", "va", "vas", "vamos", "vais", "voy",
    "son", "soy", "eres", "somos", "sois", "es",
    "he", "has", "ha", "hemos", "habéis", "han",
    # English
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "had", "her", "was", "one", "our", "out", "has", "have", "been",
    "some", "same", "also", "its", "than", "them", "they", "been",
    "into", "over", "such", "that", "this", "with", "will", "would",
    "about", "their", "there", "these", "those", "which", "while",
    "should", "could", "other", "after", "before", "between",
    "just", "like", "more", "most", "much", "only", "very",
    "well", "what", "when", "where", "whether", "why",
    "said", "say", "says", "thing", "things",
    # Code-related noise
    "def", "async", "await", "class", "return", "import", "from",
    "self", "true", "false", "none", "print", "if", "else", "elif",
    "for", "while", "try", "except", "finally", "with", "as", "pass",
    "raise", "yield", "lambda", "assert", "break", "continue",
    "in", "is", "not", "and", "or", "str", "int", "list", "dict",
    "set", "tuple", "bool", "type", "object", "value", "key",
    "file", "path", "data", "text", "code", "fn", "func",
    "error", "exception", "warning", "debug", "log", "logger",
    "none", "null", "undefined", "nan",
    # Tool-specific noise
    "tool", "tools", "call", "function", "parameter", "argument",
    "result", "output", "input", "response", "message", "session",
    "web_search", "fetch_url", "read_file", "write_file", "save_memory",
    "run_code", "execute_command", "edit_file", "search_files",
    "git_operation",
    # Exchange format noise
    "user", "assistant", "continue", "dale", "sigo", "si", "no",
}

# Minimum word length to consider
_MIN_WORD_LEN = 3
# Maximum word length
_MAX_WORD_LEN = 30
# Default number of keywords to extract
_DEFAULT_TOP_K = 5


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, filtering noise."""
    # Normalize
    text = text.lower()
    # Remove markdown, code blocks, URLs
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[`*_~\[\]#>|@]', ' ', text)
    # Split into words
    words = re.findall(r'[a-záéíóúüñ]+', text)
    # Filter
    return [
        w for w in words
        if _MIN_WORD_LEN <= len(w) <= _MAX_WORD_LEN
        and w not in _STOPWORDS
        and not w.isdigit()
    ]


def _compute_tf(tokens: list[str]) -> dict[str, float]:
    """Compute Term Frequency (normalized)."""
    if not tokens:
        return {}
    total = len(tokens)
    counts = Counter(tokens)
    return {word: count / total for word, count in counts.items()}


class TfidfExtractor:
    """TF-IDF extractor that maintains a document corpus for IDF computation.

    Usage:
        extractor = TfidfExtractor()
        extractor.add_document("exchange_1", "texto del exchange")
        keywords = extractor.extract("exchange_1")
    """

    def __init__(self):
        self._documents: dict[str, list[str]] = {}  # doc_id → tokens
        self._doc_freq: Counter[str] = Counter()     # word → how many docs contain it
        self._total_docs: int = 0

    def _add_document(self, doc_id: str, text: str) -> list[str]:
        """Internal: add a document with a specific doc_id. Returns tokens."""
        tokens = _tokenize(text)
        self._documents[doc_id] = tokens

        # Update document frequency
        unique_words = set(tokens)
        for word in unique_words:
            self._doc_freq[word] += 1
        self._total_docs += 1

        return tokens

    def add_document(self, text: str) -> list[str]:
        """Add a real document to the corpus with an auto-generated ID.
        
        Call this for every real exchange text to improve IDF values.
        """
        doc_id = f"doc_{self._total_docs}"
        return self._add_document(doc_id, text)

    def add_documents(self, texts: list[str]) -> None:
        """Batch-add multiple documents to the corpus."""
        for text in texts:
            self.add_document(text)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the corpus."""
        if doc_id in self._documents:
            tokens = self._documents.pop(doc_id)
            unique_words = set(tokens)
            for word in unique_words:
                self._doc_freq[word] -= 1
                if self._doc_freq[word] <= 0:
                    del self._doc_freq[word]
            self._total_docs -= 1

    def extract(self, doc_id: str, top_k: int = _DEFAULT_TOP_K) -> list[tuple[str, float]]:
        """Extract top-k keywords from a document by TF-IDF score.

        Returns:
            List of (word, score) tuples sorted by score descending.
        """
        if doc_id not in self._documents:
            return []

        tokens = self._documents[doc_id]
        tf = _compute_tf(tokens)
        n = max(self._total_docs, 1)

        scores: dict[str, float] = {}
        for word, freq in tf.items():
            df = self._doc_freq.get(word, 1)
            idf = math.log((n + 1) / (df + 1)) + 1.0  # smooth IDF
            scores[word] = freq * idf

        sorted_words = sorted(scores.items(), key=lambda x: -x[1])
        return sorted_words[:top_k]

    def extract_from_text(self, text: str, top_k: int = _DEFAULT_TOP_K,
                          corpus_tfidf: Optional[dict[str, float]] = None) -> list[tuple[str, float]]:
        """Extract keywords from raw text using optional precomputed IDF.

        If corpus_tfidf is provided, uses those as IDF values.
        Otherwise, uses the internal corpus IDF.
        """
        tokens = _tokenize(text)
        if not tokens:
            return []

        tf = _compute_tf(tokens)
        n = max(self._total_docs, 1)

        scores: dict[str, float] = {}
        for word, freq in tf.items():
            if corpus_tfidf and word in corpus_tfidf:
                idf = corpus_tfidf[word]
            else:
                df = self._doc_freq.get(word, 1)
                idf = math.log((n + 1) / (df + 1)) + 1.0
            scores[word] = freq * idf

        sorted_words = sorted(scores.items(), key=lambda x: -x[1])
        return sorted_words[:top_k]

    @property
    def corpus_size(self) -> int:
        return self._total_docs

    @property
    def vocabulary_size(self) -> int:
        return len(self._doc_freq)


# ── Convenience function for one-off extraction ────────────────────

logger = logging.getLogger(__name__)

# Seed with a startup corpus so IDF is meaningful
_STARTUP_CORPUS = [
    "arquitectura de software y patrones de diseno",
    "streaming de datos con async python y event loops",
    "widgets html interactivos con javascript css",
    "memoria embeddings vector search sqlite",
    "entity graph knowledge base relaciones",
    "testing pytest unit tests integration",
    "debug logging error handling exceptions",
    "performance optimization caching indexing",
    "seguridad csp cors rate limiting",
    "deploy docker uvicorn production",
    "git version control branches commits",
    "api rest fastapi endpoints routes",
    "frontend javascript react vite bundler",
    "backend async python asyncio coroutines",
    "database sqlite migrations schema",
    "tools auto discovery registry pattern",
    "system design architecture modular lego",
    "user interface ui ux experience",
    "command line cli terminal shell",
    "configuration environment variables dotenv",
]


class KeywordExtractorService:
    """Context-local TF-IDF extractor service."""

    def __init__(self, extractor: TfidfExtractor | None = None) -> None:
        self._lock = threading.Lock()
        self._extractor = extractor or self._seeded_extractor()

    @staticmethod
    def _seeded_extractor() -> TfidfExtractor:
        extractor = TfidfExtractor()
        for i, text in enumerate(_STARTUP_CORPUS):
            extractor._add_document(f"seed_{i}", text)
        return extractor

    def configure(self, extractor: TfidfExtractor | None) -> None:
        with self._lock:
            self._extractor = extractor or self._seeded_extractor()

    def add_to_corpus(self, text: str) -> None:
        with self._lock:
            self._extractor.add_document(text)

    def extract_keywords(self, text: str, top_k: int = _DEFAULT_TOP_K) -> list[tuple[str, float]]:
        with self._lock:
            return self._extractor.extract_from_text(text, top_k=top_k)


_current_service: ContextVar[KeywordExtractorService | None] = ContextVar(
    "kairos_keyword_extractor_service",
    default=None,
)


def get_service() -> KeywordExtractorService:
    """Get the context-local keyword extractor service."""
    service = _current_service.get()
    if service is None:
        service = KeywordExtractorService()
        _current_service.set(service)
    return service


logger.info("TF-IDF extractor seeded with %d documents", len(_STARTUP_CORPUS))


def configure_global_extractor(extractor: TfidfExtractor | None) -> None:
    """Set the active extractor explicitly, or clear it with None."""
    get_service().configure(extractor)


def reset_global_extractor() -> None:
    """Restore the seeded extractor for the current context."""
    _current_service.set(KeywordExtractorService())


def add_to_global_corpus(text: str) -> None:
    """Add a document to the active TF-IDF corpus to improve IDF values over time."""
    get_service().add_to_corpus(text)


def extract_keywords(text: str, top_k: int = _DEFAULT_TOP_K) -> list[tuple[str, float]]:
    """Extract keywords from text using the active TF-IDF corpus."""
    return get_service().extract_keywords(text, top_k=top_k)
