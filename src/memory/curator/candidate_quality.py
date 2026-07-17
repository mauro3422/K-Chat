"""Deterministic quality gates for curator candidate signals."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


_GENERIC_TOKENS = frozenset(
    {
        "aqui",
        "ahora",
        "alla",
        "alli",
        "antes",
        "assistant",
        "assistant_message_count",
        "available",
        "buena",
        "bueno",
        "cada",
        "channel",
        "como",
        "content",
        "content_hash",
        "cosa",
        "cosas",
        "created_at",
        "cuando",
        "despues",
        "desde",
        "dia",
        "dias",
        "dice",
        "dijo",
        "each",
        "entonces",
        "entre",
        "eres",
        "esta",
        "estamos",
        "estan",
        "estas",
        "este",
        "esto",
        "estoy",
        "extractive",
        "first",
        "forma",
        "gran",
        "hacer",
        "hecho",
        "hola",
        "keyword",
        "keywords",
        "lado",
        "last",
        "media",
        "medio",
        "message",
        "message_count",
        "messages",
        "metadata",
        "misma",
        "mismo",
        "modo",
        "mucha",
        "muchas",
        "mucho",
        "muchos",
        "nueva",
        "nuevas",
        "nuevo",
        "nuevos",
        "nunca",
        "notes",
        "only",
        "otra",
        "para",
        "parte",
        "pero",
        "poca",
        "poco",
        "porque",
        "propia",
        "propio",
        "punto",
        "session",
        "session_id",
        "side",
        "siempre",
        "sido",
        "sistema",
        "snapshot",
        "solo",
        "somos",
        "source",
        "sources",
        "sobre",
        "soy",
        "summary",
        "tal",
        "tambien",
        "tan",
        "tanto",
        "tiene",
        "tipo",
        "todo",
        "user",
        "user_message_count",
        "vamos",
        "vaya",
        "vez",
        "veces",
    }
)
_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[._-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class CandidateQuality:
    accepted: bool
    reason: str
    semantic_tokens: tuple[str, ...] = ()


def evaluate_candidate_signal(text: str) -> CandidateQuality:
    """Classify a candidate signal without using mutable corpus state."""

    normalized = unicodedata.normalize("NFKC", str(text or "")).strip("` \t\r\n")
    if "\ufffd" in normalized:
        return CandidateQuality(False, "damaged_encoding")
    if len(normalized) < 4:
        return CandidateQuality(False, "too_short")

    tokens = tuple(
        token.casefold().strip("._-")
        for token in _TOKEN_PATTERN.findall(normalized)
        if token.strip("._-")
    )
    semantic = tuple(
        token
        for token in tokens
        if len(token) >= 4
        and _fold_token(token) not in _GENERIC_TOKENS
        and not token.isdigit()
        and not re.fullmatch(r"[a-f0-9]{12,}", token)
        and not re.fullmatch(r"\d{4}-\d{2}-\d{2}t?\d*", token)
        and not re.fullmatch(r"[a-f0-9-]{20,}", token)
    )
    if not semantic:
        reason = "generic_stopword" if tokens else "no_semantic_content"
        return CandidateQuality(False, reason)
    return CandidateQuality(True, "accepted", semantic)


def _fold_token(token: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", token)
        if not unicodedata.combining(character)
    ).casefold()


def candidate_has_sufficient_signal(candidate: Mapping[str, Any]) -> bool:
    """Keep useful candidates and every item with an existing curator decision."""

    status = str(candidate.get("status") or "pending").strip()
    if status != "pending" or candidate.get("decision") or candidate.get("curation_decision"):
        return True
    signal = str(
        candidate.get("topic")
        or candidate.get("query")
        or candidate.get("value")
        or candidate.get("key")
        or candidate.get("result_excerpt")
        or ""
    )
    return evaluate_candidate_signal(signal).accepted
