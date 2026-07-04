"""Graph context formatting for layered memory retrieval."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


async def format_graph_context(
    results: list[Any],
    *,
    query: str,
    known_entities: list[str] | None = None,
    repo: Any = None,
    repos: Any = None,
    depth: int = 1,
) -> str:
    """Render nearby graph context for hybrid retrieval results."""

    graph_repo = repo or _entity_graph_repo(repos)
    if graph_repo is None:
        return ""

    lines: list[str] = []
    seen_lines: set[str] = set()
    seen_entity_ids: set[str] = set()

    def add_line(line: str) -> None:
        if line in seen_lines:
            return
        seen_lines.add(line)
        lines.append(line)

    result_nodes = result_graph_nodes(results)
    for node_id in result_nodes:
        if hasattr(graph_repo, "list_curated_relations_for_node"):
            try:
                relations = await graph_repo.list_curated_relations_for_node(node_id, limit=5)
            except Exception:
                logger.info("Curated relation lookup failed for %s", node_id, exc_info=True)
                relations = []
            for relation in relations or []:
                add_line(format_curated_relation_line(node_id, relation))

        try:
            neighbors = await graph_repo.explore_graph(node_id, depth=depth)
        except Exception:
            logger.info("Graph node exploration failed for %s", node_id, exc_info=True)
            neighbors = []
        for neighbor in (neighbors or [])[:5]:
            neighbor_name = neighbor.get("name", neighbor.get("id", "?"))
            neighbor_type = neighbor.get("entity_type", "?")
            relation = neighbor.get("relation_type", "")
            weight = neighbor.get("weight", "")
            depth_value = neighbor.get("depth", "")
            rel = f" [{relation}]" if relation else ""
            weight_hint = f" weight={weight}" if weight != "" else ""
            depth_hint = f" depth={depth_value}" if depth_value else ""
            add_line(
                f"- {node_label(node_id)} -> {neighbor_name} ({neighbor_type})"
                f"{rel}{weight_hint}{depth_hint}"
            )

    terms = entity_terms(results, query=query, known_entities=known_entities or [])
    for term in terms:
        try:
            entities = await graph_repo.search_entities(term, limit=2)
        except Exception:
            logger.info("Graph context entity search failed for %r", term, exc_info=True)
            continue

        for entity in entities or []:
            entity_id = str(entity.get("id", ""))
            if not entity_id or entity_id in seen_entity_ids:
                continue
            seen_entity_ids.add(entity_id)
            name = entity.get("name", entity_id)
            entity_type = entity.get("entity_type", "?")
            add_line(f"- {name} ({entity_type}) from `{term}`")

            try:
                neighbors = await graph_repo.explore_graph(entity_id, depth=depth)
            except Exception:
                logger.info("Graph context exploration failed for %s", entity_id, exc_info=True)
                neighbors = []

            for neighbor in (neighbors or [])[:5]:
                neighbor_name = neighbor.get("name", neighbor.get("id", "?"))
                neighbor_type = neighbor.get("entity_type", "?")
                relation = neighbor.get("relation_type", "")
                depth_value = neighbor.get("depth", "")
                rel = f" [{relation}]" if relation else ""
                depth_hint = f" depth={depth_value}" if depth_value else ""
                add_line(f"  - {neighbor_name} ({neighbor_type}){rel}{depth_hint}")

    if not lines:
        return ""
    return "## Graph context\n" + "\n".join(lines)


def entity_terms(
    results: list[Any],
    *,
    query: str,
    known_entities: list[str],
    max_terms: int = 6,
) -> list[str]:
    """Build conservative entity search terms from caller hints and results."""

    terms: list[str] = []

    def add(term: str) -> None:
        value = term.strip()
        if not value:
            return
        normalized = value.casefold()
        if normalized in {existing.casefold() for existing in terms}:
            return
        terms.append(value)

    for entity in known_entities:
        add(str(entity))

    capitalized = re.compile(r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ-]{2,}\b")
    for text in [query, *[getattr(result, "text", "") for result in results]]:
        for match in capitalized.findall(text or ""):
            add(match)
            if len(terms) >= max_terms:
                return terms

    for result in results:
        source_key = getattr(result, "source_key", "") or ""
        if ":" in source_key:
            source_key = source_key.split(":", 1)[1]
        for part in re.split(r"[-_:.\s]+", source_key):
            if len(part) >= 3:
                add(part)
                if len(terms) >= max_terms:
                    return terms

    return terms[:max_terms]


def result_graph_nodes(results: list[Any], max_nodes: int = 8) -> list[str]:
    """Derive graph node ids from layered memory result metadata."""

    nodes: list[str] = []

    def add(node_id: str) -> None:
        value = node_id.strip()
        if not value:
            return
        if value in nodes:
            return
        nodes.append(value)

    for result in results:
        source = str(getattr(result, "source", "") or "")
        source_key = str(getattr(result, "source_key", "") or "")
        if not source_key:
            continue
        if ":" in source_key and source_key.split(":", 1)[0] in {
            "memory",
            "candidate",
            "inbox",
            "inbox_group",
            "session",
            "synthesis",
            "entity",
        }:
            add(source_key)
        elif source == "memory":
            add(f"memory:{source_key}")
        elif source == "memory_candidate":
            add(f"candidate:{source_key}")
        elif source == "memory_inbox":
            add(f"inbox:{source_key}")
        elif source in {"session", "session_summary"}:
            add(f"session:{source_key}")
        elif source == "transversal_synthesis":
            add(f"synthesis:{source_key}")
        if len(nodes) >= max_nodes:
            break
    return nodes


def semantic_relation_hints(results: list[Any], *, max_hints: int = 5) -> list[dict[str, Any]]:
    """Suggest reviewable graph links from semantically close recall results."""

    hints: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    annotated: list[tuple[Any, str]] = []
    for result in results:
        nodes = result_graph_nodes([result], max_nodes=1)
        if nodes:
            annotated.append((result, nodes[0]))
        if len(annotated) >= max_hints + 1:
            break

    if len(annotated) < 2:
        return []

    anchor_result, anchor_node = annotated[0]
    for result, node_id in annotated[1:]:
        relation = _semantic_relation_type(anchor_result, result, anchor_node, node_id)
        source_id, target_id = _orient_semantic_relation(anchor_result, result, anchor_node, node_id, relation)
        identity = (source_id, target_id, relation)
        if source_id == target_id or identity in seen:
            continue
        seen.add(identity)
        weight = round(min(float(getattr(anchor_result, "fusion_score", 0.5) or 0.5), float(getattr(result, "fusion_score", 0.5) or 0.5)), 3)
        evidence = str(getattr(result, "text", "") or "").replace("\n", " ")[:180]
        hints.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation,
                "weight": weight,
                "evidence": evidence,
                "provenance": "semantic_recall_neighbor",
                "source_layer": str(getattr(result, "source", "") or ""),
                "anchor_layer": str(getattr(anchor_result, "source", "") or ""),
            }
        )
        if len(hints) >= max_hints:
            break
    return hints


def _semantic_relation_type(anchor: Any, result: Any, anchor_node: str, node_id: str) -> str:
    anchor_source = str(getattr(anchor, "source", "") or "")
    source = str(getattr(result, "source", "") or "")
    sources = {anchor_source, source}
    if "memory" in sources and "memory_candidate" in sources:
        return "REFINES"
    if "memory" in sources and ("memory_inbox" in sources or "session_summary" in sources or "transversal_synthesis" in sources):
        return "SUPPORTS"
    if anchor_node.startswith("session:") and node_id.startswith("synthesis:"):
        return "DERIVED_FROM"
    if anchor_node.startswith("synthesis:") and node_id.startswith("session:"):
        return "DERIVED_FROM"
    return "RELATED_TO"


def _orient_semantic_relation(
    anchor: Any,
    result: Any,
    anchor_node: str,
    node_id: str,
    relation_type: str,
) -> tuple[str, str]:
    anchor_source = str(getattr(anchor, "source", "") or "")
    source = str(getattr(result, "source", "") or "")
    if relation_type == "REFINES":
        if source == "memory_candidate":
            return node_id, anchor_node
        if anchor_source == "memory_candidate":
            return anchor_node, node_id
    if relation_type == "SUPPORTS":
        if source == "memory":
            return anchor_node, node_id
        if anchor_source == "memory":
            return node_id, anchor_node
    if relation_type == "DERIVED_FROM":
        if anchor_node.startswith("synthesis:"):
            return anchor_node, node_id
        if node_id.startswith("synthesis:"):
            return node_id, anchor_node
    return anchor_node, node_id


def format_curated_relation_line(node_id: str, relation: dict[str, Any]) -> str:
    source_id = str(relation.get("source_id", ""))
    target_id = str(relation.get("target_id", ""))
    other = target_id if source_id == node_id else source_id
    relation_type = relation.get("relation_type", "")
    weight = relation.get("weight", "")
    evidence = str(relation.get("evidence", "") or "").strip()
    evidence_hint = f" evidence={evidence[:90]}" if evidence else ""
    weight_hint = f" weight={weight}" if weight != "" else ""
    return f"- {node_label(node_id)} -> {node_label(other)} [curated:{relation_type}]{weight_hint}{evidence_hint}"


def node_label(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def _entity_graph_repo(repos: Any) -> Any:
    memory_repos = getattr(repos, "memory", None) if repos is not None else None
    return getattr(memory_repos, "entity_graph", None) if memory_repos is not None else None
