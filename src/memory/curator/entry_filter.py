"""Pure filtering helpers for LLM-curated memory entries."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Mapping


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9:]+", "-", _normalize_text(value)).strip("-")


def _value_body(value: str) -> str:
    return re.sub(
        r"^\s*\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?\s*\|\s*",
        "",
        value,
    ).strip()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize_text(_value_body(value)))
        if len(token) >= 3
    }


def is_trivial_curator_entry(entry: Mapping[str, str]) -> bool:
    """Reject low-value identity facts that add no useful retrieval signal."""

    key = _normalize_key(str(entry.get("key") or ""))
    if key in {
        "user:name",
        "user:nombre",
        "user:full-name",
        "user:nombre-completo",
    }:
        return True
    return bool(re.fullmatch(r"user:(?:user-name|nombre-usuario)-[a-z0-9-]+", key))


def has_allowed_curator_category(entry: Mapping[str, str]) -> bool:
    """Accept only categories described by the curator output contract."""

    key = _normalize_key(str(entry.get("key") or ""))
    category, separator, description = key.partition(":")
    return bool(
        separator
        and description
        and category in {"user", "bug", "decision", "proyecto", "patron", "checkpoint"}
    )


def curator_entry_similarity(left: Mapping[str, str], right: Mapping[str, str]) -> float:
    """Estimate semantic overlap using normalized text and token cohesion."""

    left_value = _normalize_text(_value_body(str(left.get("value") or "")))
    right_value = _normalize_text(_value_body(str(right.get("value") or "")))
    if not left_value or not right_value:
        return 0.0

    left_tokens = _tokens(left_value)
    right_tokens = _tokens(right_value)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left_value, right_value).ratio()
    return max(jaccard, sequence)


def curator_entries_are_duplicates(
    left: Mapping[str, str],
    right: Mapping[str, str],
    *,
    similarity_threshold: float = 0.72,
) -> bool:
    left_key = _normalize_key(str(left.get("key") or ""))
    right_key = _normalize_key(str(right.get("key") or ""))
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_category = left_key.partition(":")[0]
    right_category = right_key.partition(":")[0]
    return (
        left_category == right_category
        and curator_entry_similarity(left, right) >= similarity_threshold
    )


def filter_curator_entries(
    entries: Iterable[Mapping[str, str]],
    *,
    similarity_threshold: float = 0.72,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Drop trivial and semantically duplicate curator entries.

    Exact keys are treated as the same memory. For semantic matching, entries
    must share a category so an unrelated ``bug:`` and ``decision:`` cannot be
    collapsed merely because their wording overlaps.
    """

    kept: list[dict[str, str]] = []
    stats = {"input": 0, "kept": 0, "trivial": 0, "invalid_category": 0, "duplicates": 0}

    for raw_entry in entries:
        stats["input"] += 1
        entry = {
            "key": str(raw_entry.get("key") or "").strip(),
            "value": str(raw_entry.get("value") or "").strip(),
        }
        if not entry["key"] or not entry["value"] or is_trivial_curator_entry(entry):
            stats["trivial"] += 1
            continue
        if not has_allowed_curator_category(entry):
            stats["invalid_category"] += 1
            continue

        duplicate_index: int | None = None
        for index, existing in enumerate(kept):
            if curator_entries_are_duplicates(
                entry,
                existing,
                similarity_threshold=similarity_threshold,
            ):
                duplicate_index = index
                break

        if duplicate_index is None:
            kept.append(entry)
            continue

        stats["duplicates"] += 1
        if len(_tokens(entry["value"])) > len(_tokens(kept[duplicate_index]["value"])):
            kept[duplicate_index] = entry

    stats["kept"] = len(kept)
    return kept, stats
