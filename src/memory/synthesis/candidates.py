"""Candidate generation from session summary artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from src.memory import paths as memory_paths

_project_root = memory_paths._project_root
_default_target_date = memory_paths._default_target_date


def _candidate_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _candidate_signal_lines(text: str) -> list[str]:
    signal_words = (
        "prefiere", "quiere", "decidio", "decidió", "decisión", "decision", "bug",
        "error", "falla", "pendiente", "plan", "roadmap", "memoria",
        "embedding", "curador", "curaduria", "curaduría", "pipeline", "telegram", "laptop",
    )
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith("#"):
            continue
        low = line.lower()
        if any(word in low for word in signal_words):
            lines.append(line)
        if len(lines) >= 8:
            break
    return lines


def _candidate_entity_hints(lines: list[str], artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Infer lightweight entity hints for curator review."""

    text = " ".join(lines)
    hints = (
        ("Mauro", "person", ("mauro",)),
        ("Kairos", "project", ("kairos", "k-chat")),
        ("k-chat", "project", ("k-chat", "k chat")),
        ("Codex", "agent", ("codex",)),
        ("Telegram", "channel", ("telegram",)),
        ("PC", "device", ("pc",)),
        ("laptop", "device", ("laptop", "notebook")),
        ("MEMORY.md", "artifact", ("memory.md", "memory")),
        ("memoria", "concept", ("memoria", "memory")),
        ("embedding", "technology", ("embedding", "embeddings", "vector")),
        ("grafo", "concept", ("grafo", "grafos", "graph")),
        ("curador", "role", ("curador", "curadores", "curaduria")),
        ("pipeline", "system", ("pipeline",)),
    )
    lowered = text.lower()
    entities: list[dict[str, Any]] = []
    for name, entity_type, needles in hints:
        if any(needle in lowered for needle in needles):
            entities.append(
                {
                    "name": name,
                    "entity_type": entity_type,
                    "confidence": 0.7,
                    "evidence": next((line for line in lines if any(needle in line.lower() for needle in needles)), lines[0]),
                }
            )

    channel = str(artifact.get("channel") or "")
    if channel and not any(item["name"] == channel for item in entities):
        entities.append(
            {
                "name": channel,
                "entity_type": "channel",
                "confidence": 0.55,
                "evidence": "session metadata",
            }
        )

    # PMI is a corpus-level coherence signal, not an entity extractor.  Its
    # vocabulary also contains UI labels, code identifiers and test fixtures;
    # promoting every PMI token into a graph node creates noisy connections.
    # Keep the metadata for diagnostics, but only emit the curated hints above.

    return entities


def _candidate_temporal_metadata(timestamp: str) -> dict[str, str]:
    return {
        "first_seen": timestamp,
        "last_seen": timestamp,
        "status": "new",
    }


def _candidate_relation_policy(lines: list[str], session_id: str) -> dict[str, Any]:
    """Infer the curator-facing relation intent from summary language."""

    text = " ".join(lines).lower()
    rules = (
        (
            "CONTRADICTS",
            "memory:canonical",
            0.68,
            "summary_contradiction_signal",
            (
                "contradice",
                "contradiccion",
                "contradicción",
                "conflicto",
                "ya no",
                "en vez de",
                "cambio de decision",
                "cambio de decisión",
            ),
        ),
        (
            "REFINES",
            "memory:canonical",
            0.66,
            "summary_refinement_signal",
            (
                "refina",
                "refinar",
                "ajusta",
                "ajustar",
                "precisa",
                "mas especifico",
                "más específico",
                "mejorar metadata",
                "metadata",
            ),
        ),
        (
            "LINKS_TO",
            "memory:semantic-neighbor",
            0.64,
            "summary_link_signal",
            (
                "relaciona",
                "relacionar",
                "conecta",
                "conectar",
                "enlaza",
                "enlazar",
                "link",
                "transversal",
                "semantica",
                "semántica",
            ),
        ),
    )
    for relation_type, target_id, confidence, reason, needles in rules:
        if any(needle in text for needle in needles):
            return {
                "relation_type": relation_type,
                "target_id": target_id,
                "confidence": confidence,
                "reason": reason,
                "target_needs_resolution": True,
            }
    return {
        "relation_type": "DERIVED_FROM",
        "target_id": f"session:{session_id}" if session_id else "session:unknown",
        "confidence": 0.62,
        "reason": "session_summary_signal",
        "target_needs_resolution": False,
    }


def _candidate_relation_hints(
    candidate_id: str,
    session_id: str,
    artifact_path: str,
    entities: list[dict[str, Any]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Propose graph edges without mutating the graph."""

    session_node = f"session:{session_id}" if session_id else "session:unknown"
    relations: list[dict[str, Any]] = [
        {
            "source_id": f"candidate:{candidate_id}",
            "target_id": session_node,
            "relation_type": "DERIVED_FROM",
            "weight": 0.72,
            "provenance": "session_summary_candidate",
        }
    ]
    policy_relation = str(policy.get("relation_type") or "")
    policy_target = str(policy.get("target_id") or "")
    if policy_relation and policy_relation != "DERIVED_FROM" and policy_target:
        relations.append(
            {
                "source_id": f"candidate:{candidate_id}",
                "target_id": policy_target,
                "relation_type": policy_relation,
                "weight": float(policy.get("confidence") or 0.5),
                "provenance": str(policy.get("reason") or "session_summary_relation_signal"),
                "needs_resolution": bool(policy.get("target_needs_resolution")),
            }
        )
    if artifact_path:
        relations.append(
            {
                "source_id": f"candidate:{candidate_id}",
                "target_id": f"artifact:{hashlib.sha256(artifact_path.encode('utf-8')).hexdigest()[:16]}",
                "relation_type": "DERIVED_FROM",
                "weight": 0.62,
                "provenance": "session_summary_artifact",
            }
        )
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        if not name:
            continue
        relations.append(
            {
                "source_id": session_node,
                "target_id": f"entity:{name.lower().replace(' ', '_')}",
                "relation_type": "MENTIONS",
                "weight": float(entity.get("confidence") or 0.5),
                "provenance": "session_summary_signal",
            }
        )
    return relations


def candidates_from_session_summary_artifact(
    artifact: Mapping[str, Any],
    timestamp: str | None = None,
    scorer: "CombinedScorer | None" = None,
) -> list[dict[str, Any]]:
    """Create conservative review candidates from a summary artifact.

    When ``scorer`` is provided, candidate confidence is enhanced with
    keyword-significance, entity-centrality, and semantic-novelty boosts.
    """

    text = str(artifact.get("text") or "")
    lines = _candidate_signal_lines(text)
    if not lines:
        return []

    from src.memory.synthesis.session import _clip

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    session_id = str(artifact.get("session_id") or "")
    channel = str(artifact.get("channel") or "web")
    artifact_path = str(artifact.get("path") or "")
    query = " ".join(line.lstrip("- ").strip() for line in lines[:3])
    entities = _candidate_entity_hints(lines, artifact)
    policy = _candidate_relation_policy(lines, session_id)
    base_confidence = float(policy["confidence"])
    candidate_text = " ".join(lines)

    # --- Enhance confidence with mathematical scoring ---
    if scorer is not None:
        from src.memory.analysis.corpus import tokenize_doc

        tokens = tokenize_doc(candidate_text)
        term_counts: dict[str, int] = {}
        for t in tokens:
            term_counts[t] = term_counts.get(t, 0) + 1
        if term_counts:
            doc_len = len(tokens) + 1
            kw_scores = scorer.score_keywords_batch(
                list(term_counts.items()), doc_len
            )
        else:
            kw_scores = []

        entity_names = [str(e.get("name", "")) for e in entities if e.get("name")]

        # Read pre-computed coherence + reliability from artifact metadata
        meta = artifact.get("metadata") or {}
        lsa_coherence = float(meta.get("lsa_coherence", 0.0))
        lsa_reliability = float(meta.get("lsa_reliability", 0.0))
        cross_pmi_score = float(meta.get("cross_pmi_score", 0.0))
        pmi_reliability = float(meta.get("pmi_reliability", 0.0))

        try:
            from src.memory.analysis.scoring import candidate_confidence_from_scores
        except ImportError:
            final_confidence = base_confidence
            link_score = base_confidence
            link_reasons = [str(policy.get("reason", "session_summary_signal")), "summary_entity_hints"]
        else:
            enhanced_confidence = candidate_confidence_from_scores(
                kw_scores,
                entity_names,
                session_text=candidate_text,
                scorer=scorer,
                base_confidence=base_confidence,
                lsa_coherence=lsa_coherence,
                lsa_reliability=lsa_reliability,
                cross_pmi_score=cross_pmi_score,
                pmi_reliability=pmi_reliability,
            )
            final_confidence = enhanced_confidence
            link_score = enhanced_confidence
            link_reasons = [
                str(policy.get("reason", "session_summary_signal")),
                "enhanced_scoring",
            ]
    else:
        final_confidence = base_confidence
        link_score = base_confidence
        link_reasons = [str(policy.get("reason", "session_summary_signal")), "summary_entity_hints"]

    payload = {
        "type": "session_summary_candidate",
        "source": "session_summary",
        "session_id": session_id,
        "channel": channel,
        "query": _clip(query, 500),
        "result_excerpt": _clip("\n".join(lines), 900),
        "source_artifact": artifact_path,
        "artifact": artifact_path,
        "content_hash": str(artifact.get("content_hash") or ""),
    }
    candidate_id = _candidate_id(payload)
    return [
        {
            **payload,
            "candidate_id": candidate_id,
            "status": "pending",
            "created_at": ts,
            "confidence": round(final_confidence, 4),
            "relation_type": str(policy["relation_type"]),
            "source_id": f"candidate:{candidate_id}",
            "target_id": str(policy["target_id"]),
            "target_needs_resolution": bool(policy["target_needs_resolution"]),
            "link_score": round(link_score, 4),
            "link_reasons": link_reasons,
            "entities": entities,
            "temporal": _candidate_temporal_metadata(ts),
            "provenance": {
                "session_id": session_id,
                "channel": channel,
                "artifact": artifact_path,
                "content_hash": str(artifact.get("content_hash") or ""),
            },
            "proposed_relations": _candidate_relation_hints(
                candidate_id,
                session_id,
                artifact_path,
                entities,
                policy,
            ),
        }
    ]


def generate_session_summary_candidates(
    root: str | Path | None = None,
    target_date: date | None = None,
    timestamp: str | None = None,
    scorer: "CombinedScorer | None" = None,
) -> dict[str, Any]:
    """Materialize reviewable candidates derived from session summaries.

    Parameters
    ----------
    scorer : CombinedScorer | None
        Optional mathematical scorer for enhanced confidence estimation.
    """

    from src.memory.curator.recall_review import load_candidates, write_candidates
    from src.memory.synthesis.session import _build_scorer, discover_session_summary_artifacts, session_summary_candidate_path

    try:
        from src.memory.analysis.scoring import compute_statistical_thresholds
    except ImportError:
        def compute_statistical_thresholds(confidences: list[float]) -> dict[str, float]:
            return {"auto_promote_threshold": 1.0, "review_threshold": 0.0}

    target = target_date or _default_target_date()
    path = session_summary_candidate_path(target, root=root)
    existing = load_candidates(path)
    by_id = {str(candidate.get("candidate_id")): dict(candidate) for candidate in existing}
    created = 0
    refreshed = 0

    # Build scorer if not provided
    if scorer is None:
        scorer = _build_scorer(root=root)

    # First pass: generate all candidates
    new_candidates: list[dict[str, Any]] = []
    for artifact in discover_session_summary_artifacts(root=root):
        for candidate in candidates_from_session_summary_artifact(
            artifact, timestamp=timestamp, scorer=scorer
        ):
            cid = str(candidate.get("candidate_id") or "")
            if cid in by_id:
                previous = by_id[cid]
                merged = dict(candidate)
                # Rebuild derived fields (entities, relations, confidence)
                # while preserving any human decision already recorded.
                for key in ("status", "promotion_decision", "decision", "created_at"):
                    if key in previous:
                        merged[key] = previous[key]
                by_id[cid] = merged
                refreshed += 1
                continue
            new_candidates.append(candidate)

    # Second pass: compute batch statistical thresholds and add promotion_decision
    if new_candidates:
        confidences = [float(c.get("confidence", 0)) for c in new_candidates]
        thresh = compute_statistical_thresholds(confidences)
        for c in new_candidates:
            conf = float(c.get("confidence", 0))
            if conf >= thresh["auto_promote_threshold"]:
                # Statistical confidence is prioritization, not ground truth.
                # Automatic promotion stays disabled until a human-labelled
                # benchmark explicitly calibrates and approves the policy.
                c["promotion_decision"] = "review"
                c["promotion_gate"] = "human_benchmark_required"
            elif conf >= thresh["review_threshold"]:
                c["promotion_decision"] = "review"
            else:
                c["promotion_decision"] = "hold"
            by_id[str(c.get("candidate_id"))] = c
            created += 1

    if by_id:
        write_candidates(path, list(by_id.values()))
    return {
        "path": str(path),
        "created": created,
        "refreshed": refreshed,
        "total": len(by_id),
    }
