"""Reusable curator queue builders.

The queue is intentionally artifact-oriented: it turns inbox groups,
candidate cards, and relation hints into prioritized work items that can feed
the morning report, tools, or a future UI without duplicating policy.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def priority_for_inbox(item: Mapping[str, Any]) -> int:
    """Return a stable priority for an inbox group."""

    urgency = str(item.get("urgency") or "normal").lower()
    if urgency == "high":
        return 90
    if urgency == "low":
        return 35
    return 60


def priority_for_candidate(card: Mapping[str, Any]) -> int:
    """Return a stable priority for a candidate card."""

    score = float(card.get("score") or 0.0)
    missing = card.get("metadata_missing") or []
    base = int(score * 100)
    if missing:
        return max(base, 65)
    return base


def priority_for_ready_candidate(card: Mapping[str, Any]) -> int:
    """Ready promotions should float above ordinary review work."""

    return max(88, priority_for_candidate(card))


def inbox_queue_item(group: Mapping[str, Any]) -> dict[str, Any]:
    """Build a queue item for a coalesced inbox group."""

    key = str(group.get("key") or "").strip()
    value = str(group.get("value") or "").strip()
    label = key or value[:80] or str(group.get("group_id", "inbox"))
    reinforcement = int(group.get("reinforcement_count") or 1)
    reinforcement_text = f" reforzado={reinforcement}" if reinforcement > 1 else ""
    group_id = str(group.get("group_id") or "")
    inspect_command = (
        f"review_memory_inbox action=inspect group_id={group_id} include_recall_context=true"
        if group_id
        else ""
    )
    promote_command = f"review_memory_inbox action=promote group_id={group_id}" if group_id else ""
    reject_command = f"review_memory_inbox action=reject group_id={group_id}" if group_id else ""
    return {
        "priority": priority_for_inbox(group),
        "kind": "inbox",
        "id": group_id,
        "title": f"Curar inbox: {label}",
        "detail": (
            f"{value[:180]}{reinforcement_text}; inspect={inspect_command}; "
            f"promote={promote_command}"
        ),
        "artifact": (group.get("artifacts") or [""])[0],
        "next_action": "inspect_inbox",
        "recommended_command": inspect_command,
        "fallback_command": reject_command,
        "followup_command": promote_command,
        "why": ["temporary_memory_pending_review"],
        "reinforcement_count": reinforcement,
        "inbox_ids": group.get("inbox_ids", []),
        "artifacts": group.get("artifacts", []),
        "inspect_command": inspect_command,
        "promote_command": promote_command,
        "reject_command": reject_command,
    }


def candidate_queue_item(card: Mapping[str, Any]) -> dict[str, Any]:
    """Build a queue item for a pending candidate card."""

    title = str(card.get("query") or card.get("candidate_id") or "candidate")
    missing = list(card.get("metadata_missing") or [])
    action = "Completar metadata" if missing else "Revisar/promover candidato"
    review_command = str(card.get("review_command") or "")
    map_command = str(card.get("map_command") or "")
    next_action = "complete_metadata" if missing else str(card.get("recommendation") or "review")
    recommended_command = review_command
    if not missing and map_command:
        recommended_command = map_command
    return {
        "priority": priority_for_candidate(card),
        "kind": "candidate",
        "id": card.get("candidate_id", ""),
        "title": f"{action}: {title[:100]}",
        "detail": (
            f"{card.get('recommendation')} score={card.get('score')} "
            f"missing={', '.join(missing)}; explain={review_command} "
            f"map={map_command}"
        ),
        "artifact": card.get("artifact", ""),
        "next_action": next_action,
        "recommended_command": recommended_command,
        "why": list(card.get("reasons") or []),
        "metadata_missing": missing,
        "review_command": review_command,
        "map_command": map_command,
    }


def ready_candidate_queue_item(card: Mapping[str, Any]) -> dict[str, Any]:
    """Build a queue item for a candidate ready to promote."""

    title = str(card.get("query") or card.get("candidate_id") or "candidate")
    promotion_command = str(card.get("promotion_command") or "")
    preview_command = str(card.get("relation_preview_command") or "")
    recommended_command = preview_command or promotion_command
    return {
        "priority": priority_for_ready_candidate(card),
        "kind": "candidate_ready",
        "id": card.get("candidate_id", ""),
        "title": f"Revisar/promover candidato listo: {title[:100]}",
        "detail": (
            f"preview={preview_command}; promote={promotion_command} "
            f"relation={card.get('relation_type')} score={card.get('score')}"
        ),
        "artifact": card.get("artifact", ""),
        "next_action": "preview_relations" if preview_command else "promote_ready",
        "recommended_command": recommended_command,
        "followup_command": promotion_command if preview_command else "",
        "why": ["ready_for_promotion"],
        "review_command": card.get("review_command", ""),
        "map_command": card.get("map_command", ""),
        "relation_preview_command": preview_command,
        "promotion_command": promotion_command,
    }


def relation_hint_queue_item(
    decisions: Sequence[Mapping[str, Any]],
    *,
    preview_command: str = "curator_workbench action=preview_hints",
    materialize_command: str = "curator_workbench action=materialize_hints",
) -> dict[str, Any] | None:
    """Build one queue item for pending relation hints, if any exist."""

    relation_hint_count = 0
    relation_hint_decisions = 0
    for decision in decisions:
        hints = decision.get("relation_hints") or []
        if not isinstance(hints, list) or not hints:
            continue
        relation_hint_decisions += 1
        relation_hint_count += len(hints)
    if not relation_hint_count:
        return None
    return {
        "priority": 82,
        "kind": "relation_hints",
        "id": "curation-relation-hints",
        "title": "Materializar relaciones sugeridas por decisiones",
        "detail": (
            f"{relation_hint_count} relation_hints en "
            f"{relation_hint_decisions} decision(es); preview={preview_command}; "
            f"materialize={materialize_command}"
        ),
        "artifact": (decisions[0].get("_artifact") if decisions else "") or "",
        "next_action": "preview_hints",
        "recommended_command": preview_command,
        "followup_command": materialize_command,
        "why": ["curated_relation_hints_pending"],
        "preview_command": preview_command,
        "materialize_command": materialize_command,
        "relation_hint_count": relation_hint_count,
        "decision_count": relation_hint_decisions,
    }


def semantic_recall_hint_queue_item(
    candidate_cards: Sequence[Mapping[str, Any]],
    *,
    recall_action: str = "curator_workbench action=recall_packet",
) -> dict[str, Any] | None:
    """Build a queue item to derive reviewable graph hints from semantic recall."""

    candidates = [
        card for card in candidate_cards
        if str(card.get("query") or "").strip() and str(card.get("status") or "pending") == "pending"
        and not str(card.get("map_command") or "").strip()
    ]
    if not candidates:
        return None

    anchor = max(candidates, key=lambda card: float(card.get("score") or 0.0))
    query = str(anchor.get("query") or "").replace('"', "'").strip()
    candidate_id = str(anchor.get("candidate_id") or "")
    command = f'{recall_action} query="{query}" source="" limit=8'
    return {
        "priority": 64,
        "kind": "semantic_relation_hints",
        "id": candidate_id or "semantic-recall-hints",
        "title": "Proponer relaciones desde vecinos semanticos",
        "detail": (
            f"{len(candidates)} candidato(s) pendiente(s) con texto semantico; "
            f"anchor={candidate_id}; recall={command}"
        ),
        "artifact": anchor.get("artifact", ""),
        "next_action": "recall_packet",
        "recommended_command": command,
        "why": ["semantic_neighbors_need_graph_review"],
        "candidate_count": len(candidates),
        "anchor_candidate_id": candidate_id,
    }


def build_curation_queue(
    *,
    inbox_groups: Sequence[Mapping[str, Any]] = (),
    candidate_cards: Sequence[Mapping[str, Any]] = (),
    ready_candidate_cards: Sequence[Mapping[str, Any]] = (),
    curation_decisions: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Build the prioritized curator queue across memory layers."""

    actions: list[dict[str, Any]] = []
    actions.extend(inbox_queue_item(item) for item in inbox_groups)
    actions.extend(candidate_queue_item(card) for card in candidate_cards)
    actions.extend(ready_candidate_queue_item(card) for card in ready_candidate_cards)
    semantic_item = semantic_recall_hint_queue_item(candidate_cards)
    if semantic_item is not None:
        actions.append(semantic_item)
    relation_item = relation_hint_queue_item(curation_decisions)
    if relation_item is not None:
        actions.append(relation_item)
    return sorted(actions, key=lambda item: int(item.get("priority") or 0), reverse=True)
