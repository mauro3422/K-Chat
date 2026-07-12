"""Evidence-based freshness audit for curator candidates."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


def audit_bug_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    project_text: str = "",
    documentation_text: str = "",
) -> list[dict[str, Any]]:
    """Classify bug candidates without pretending text presence proves a fix.

    A bug is only marked ``resolved`` when an explicit closure marker exists in
    project documentation. Otherwise it remains ``open_or_unverified``.
    """
    corpus = f"{project_text}\n{documentation_text}".lower()
    audited: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        key = str(item.get("key") or "")
        if not key.startswith("bug:"):
            item["vigency"] = "not_a_bug"
        else:
            slug = re.escape(key.split(":", 1)[1]).replace(r"\-", "[-_ ]")
            marker = r"\b(?:resolved|fixed|corregid[oa]|cerrad[oa])\b"
            target = rf"(?:\b{re.escape(key)}\b|\b{slug}\b)"
            closed = bool(re.search(
                rf"(?:{marker}.{{0,100}}{target}|{target}.{{0,100}}{marker})",
                corpus,
                re.IGNORECASE | re.DOTALL,
            ))
            item["vigency"] = "resolved" if closed else "open_or_unverified"
            item["requires_code_review"] = not closed
        audited.append(item)
    return audited
