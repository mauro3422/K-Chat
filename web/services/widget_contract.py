"""Shared widget rendering contract for server-side services."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

WIDGET_STATE_CODE_PREFIX = "_code_"
INLINE_WIDGET_BLOCK_RE = re.compile(r"```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```")


def normalize_inline_widget_code(code: str) -> str:
    """Normalize inline widget code before it is stored as persisted state."""
    return code.replace("?.", ".")


def extract_inline_widget_states(messages: Iterable[Sequence[Any]]) -> dict[str, str]:
    """Extract inline widget code blocks as persisted widget code entries, ignoring patterns inside standard code blocks."""
    combined_text = "\n".join(
        str(row["content"])
        for row in messages
        if len(row) > 1 and row["role"] == "assistant" and row["content"]
    )

    # Find ignored ranges (standard code blocks and inline code blocks)
    ignored_ranges: list[tuple[int, int]] = []
    for m in re.finditer(r"```(?!html-widget)[\s\S]*?(?:```|$)", combined_text):
        ignored_ranges.append((m.start(), m.end()))
    for m in re.finditer(r"`[^`\n]+`", combined_text):
        ignored_ranges.append((m.start(), m.end()))

    def is_ignored(pos: int) -> bool:
        for start, end in ignored_ranges:
            if start <= pos < end:
                return True
        return False

    widget_states: dict[str, str] = {}
    for match in INLINE_WIDGET_BLOCK_RE.finditer(combined_text):
        if is_ignored(match.start()):
            continue
        key = match.group(1)
        code = normalize_inline_widget_code(match.group(2))
        if key and code:
            widget_states[f"{WIDGET_STATE_CODE_PREFIX}{key}"] = code
    return widget_states
