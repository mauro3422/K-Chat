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
    """Extract inline widget code blocks as persisted widget code entries."""
    combined_text = "\n".join(
        str(row[1])
        for row in messages
        if len(row) > 1 and row[0] == "assistant" and row[1]
    )

    widget_states: dict[str, str] = {}
    for match in INLINE_WIDGET_BLOCK_RE.finditer(combined_text):
        key = match.group(1)
        code = normalize_inline_widget_code(match.group(2))
        if key and code:
            widget_states[f"{WIDGET_STATE_CODE_PREFIX}{key}"] = code
    return widget_states
