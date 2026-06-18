import os
import time
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Final

from src.context.files import _ensure_file, _read_file
from src.context.templates import TEMPLATES
from src.context.tools_docs import _build_rules_files, _build_tools_md
from src.paths import CONTEXT_DIR

RULES_DIR: Final[str] = os.path.join(CONTEXT_DIR, "rules")
TOOLS_PATH: Final[str] = os.path.join(CONTEXT_DIR, "TOOLS.md")

CACHE_TTL_SECONDS: Final[float] = 30.0
_CONTEXT_CACHE: str | None = None
_CACHE_TIMESTAMP: float = 0.0
_TOOLS_MD_CACHE: str | None = None
_CACHE_LOCK = threading.Lock()

_invalidate_marker_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".kairos", "invalidate_cache")


def _check_invalidate_marker() -> bool:
    """Check if watchdog requested cache invalidation."""
    if os.path.exists(_invalidate_marker_path):
        try:
            os.unlink(_invalidate_marker_path)
            return True
        except Exception:
            pass
    return False


@dataclass(frozen=True)
class ContextSnapshot:
    text: str
    tools_md: str


def _write_if_changed(path: str, content: str) -> None:
    current = _read_file(path)
    if current != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def build_context_snapshot(force: bool = False, tool_definitions: dict[str, Any] | None = None) -> ContextSnapshot:
    global _CONTEXT_CACHE, _CACHE_TIMESTAMP, _TOOLS_MD_CACHE

    if _check_invalidate_marker():
        with _CACHE_LOCK:
            _CONTEXT_CACHE = None
            _CACHE_TIMESTAMP = 0.0
            _TOOLS_MD_CACHE = None

    with _CACHE_LOCK:
        if _CONTEXT_CACHE is not None and _TOOLS_MD_CACHE is not None and not force:
            if time.time() - _CACHE_TIMESTAMP < CACHE_TTL_SECONDS:
                return ContextSnapshot(text=_CONTEXT_CACHE, tools_md=_TOOLS_MD_CACHE)
            _CONTEXT_CACHE = None

    segments: list[str] = []
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        _ensure_file(filepath, TEMPLATES[filename])
        content = _read_file(filepath)
        if content:
            segments.append(content)

    if tool_definitions is not None:
        _build_rules_files(RULES_DIR, tool_definitions=tool_definitions)
        tools_md = _build_tools_md(tool_definitions=tool_definitions)
        _write_if_changed(TOOLS_PATH, tools_md)
    else:
        tools_md = ""

    with _CACHE_LOCK:
        _CONTEXT_CACHE = "\n\n".join(segments)
        _CACHE_TIMESTAMP = time.time()
        _TOOLS_MD_CACHE = tools_md
    return ContextSnapshot(text=_CONTEXT_CACHE, tools_md=tools_md)

def get_context_text(force: bool = False) -> str:
    return build_context_snapshot(force=force).text


def invalidate_context_cache() -> None:
    """Force rebuild of context cache on next build_context_snapshot() call.

    Call this after modifying any source .md file (SOUL.md, MEMORY.md, AGENTS.md)
    to ensure the next system prompt reflects the latest changes.
    """
    global _CONTEXT_CACHE, _CACHE_TIMESTAMP, _TOOLS_MD_CACHE
    with _CACHE_LOCK:
        _CONTEXT_CACHE = None
        _CACHE_TIMESTAMP = 0.0
        _TOOLS_MD_CACHE = None


def reset_context_cache() -> None:
    """Alias for invalidate_context_cache() to match other lifecycle helpers."""
    invalidate_context_cache()
