"""Data models for vector storage and retrieval."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VectorEntry:
    """A vector entry in the sqlite-vec store."""
    id: Optional[int] = None
    source: str = ""           # "memory" (MEMORY.md) or "session" (exchange)
    source_key: str = ""       # For memory: the key; for session: session_id
    exchange_idx: int = 0      # Exchange index within a session
    text: str = ""             # Original text
    embedding: list = field(default_factory=list)
    metadata: str = "{}"       # JSON string
    created_at: str = ""

    @property
    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "source_key": self.source_key,
            "exchange_idx": self.exchange_idx,
            "text_preview": self.text[:100],
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class SearchResult:
    """Result of a similarity search."""
    entry: VectorEntry
    distance: float = 0.0
    score: float = 0.0  # 1 - distance, higher = more similar
