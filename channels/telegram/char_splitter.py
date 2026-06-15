"""Char splitter — splits long texts into Telegram-safe chunks.

Telegram limits message text to 4096 characters. This component splits
at word boundaries to avoid cutting words in half, with a configurable
safety margin (default 4000).
"""

from __future__ import annotations

import re
from channels.telegram.protocols import CharSplitterProtocol


class CharSplitter:
    """Splits text into chunks of at most ``max_chars`` characters.

    Splits at word boundaries (whitespace/newlines) when possible.
    Falls back to hard character split for texts without spaces.
    """

    MAX_CHARS = 4000

    def split(self, text: str, max_chars: int | None = None) -> list[str]:
        """Split text into Telegram-safe chunks.

        Args:
            text: The text to split.
            max_chars: Maximum chunk length (default: ``MAX_CHARS``).

        Returns:
            A list of text chunks. Single element if text fits.
        """
        if not text:
            return [""]

        limit = max_chars or self.MAX_CHARS
        if len(text) <= limit:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break

            # Try to split at the last whitespace before the limit
            chunk = remaining[:limit]
            split_pos = self._last_word_boundary(chunk)

            if split_pos > 0:
                chunks.append(remaining[:split_pos].rstrip())
                remaining = remaining[split_pos:].lstrip()
            else:
                # No word boundary found — hard split
                chunks.append(chunk)
                remaining = remaining[limit:]

        return chunks

    @staticmethod
    def _last_word_boundary(text: str) -> int:
        """Find the last word boundary position in text.

        Searches for the last whitespace character. Returns -1 if none.
        """
        # Look for newlines first (preferred split point)
        nl = text.rfind("\n")
        if nl > len(text) // 2:
            return nl + 1  # Include the newline in the current chunk

        # Then spaces
        sp = text.rfind(" ")
        if sp > len(text) // 2:
            return sp + 1

        # Fall back to any whitespace
        match = re.search(r"\s", text[::-1])
        if match:
            pos = len(text) - match.start()
            if pos > len(text) // 2:
                return pos

        return -1
