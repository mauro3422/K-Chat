import os
from dataclasses import dataclass
from typing import Final

from src.context.files import _ensure_file, _read_file
from src.context.templates import TEMPLATES
from src.context.tools_docs import _build_rules_files, _build_tools_md
from src.paths import CONTEXT_DIR

RULES_DIR: Final[str] = os.path.join(CONTEXT_DIR, "rules")
TOOLS_PATH: Final[str] = os.path.join(CONTEXT_DIR, "TOOLS.md")

_CONTEXT_CACHE: str | None = None
_TOOLS_MD_CACHE: str | None = None


@dataclass(frozen=True)
class ContextSnapshot:
    text: str
    tools_md: str


def _write_if_changed(path: str, content: str) -> None:
    current = _read_file(path)
    if current != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def build_context_snapshot(force: bool = False) -> ContextSnapshot:
    global _CONTEXT_CACHE, _TOOLS_MD_CACHE

    if _CONTEXT_CACHE is not None and _TOOLS_MD_CACHE is not None and not force:
        return ContextSnapshot(text=_CONTEXT_CACHE, tools_md=_TOOLS_MD_CACHE)

    segments: list[str] = []
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        _ensure_file(filepath, TEMPLATES[filename])
        content = _read_file(filepath)
        if content:
            segments.append(content)

    _build_rules_files(RULES_DIR)
    tools_md = _build_tools_md()
    _write_if_changed(TOOLS_PATH, tools_md)

    _CONTEXT_CACHE = "\n\n".join(segments)
    _TOOLS_MD_CACHE = tools_md
    return ContextSnapshot(text=_CONTEXT_CACHE, tools_md=tools_md)

def get_context_text(force: bool = False) -> str:
    return build_context_snapshot(force=force).text


def invalidate_context_cache() -> None:
    """Force rebuild of context cache on next build_context_snapshot() call.

    Call this after modifying any source .md file (SOUL.md, MEMORY.md, AGENTS.md)
    to ensure the next system prompt reflects the latest changes.
    """
    global _CONTEXT_CACHE, _TOOLS_MD_CACHE
    _CONTEXT_CACHE = None
    _TOOLS_MD_CACHE = None
