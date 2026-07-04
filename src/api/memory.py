"""Memory API facade — re-exports for web/ layer consumption.

Architecture: web/ → src/api/ → src/memory/
The web layer must go through this facade instead of importing src/memory/ directly.
"""

from src.memory.content_hash import content_hash
from src.memory.embedding_identity import session_exchange_embedding_identity
from src.memory.embeddings.service import generate_embeddings_batch

__all__ = ["content_hash", "session_exchange_embedding_identity", "generate_embeddings_batch"]
