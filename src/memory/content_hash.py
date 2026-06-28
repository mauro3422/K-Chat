"""Shared content hashing helpers for memory vectors and work catalog."""

from __future__ import annotations

import hashlib
import re


def normalize_for_content_hash(text: str) -> str:
    """Normalize text before content hashing.

    This intentionally matches the session vectorizer behavior: code blocks and
    inline code are ignored, casing is folded, and whitespace is collapsed.
    """
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", "", text)
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


def raw_text_hash(text: str, *, limit: int = 4000) -> str:
    return hashlib.md5(text[:limit].encode()).hexdigest()


def content_hash(text: str, *, limit: int = 4000) -> str:
    return hashlib.md5(normalize_for_content_hash(text[:limit]).encode()).hexdigest()


def memory_hashes(value: str) -> tuple[str, str]:
    """Return (raw_hash, normalized_content_hash) for a memory value."""
    return raw_text_hash(value), content_hash(value)
