"""Token budget management for memory injection."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenBudgetConfig:
    """Configuration for token budget."""
    max_tokens: int = 3000           # Max tokens for all memories combined
    per_result_tokens: int = 200     # Estimated tokens per result
    max_results: int = 15            # Hard limit on results
    truncate_to_chars: int = 300     # Truncate each result text to this


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for Spanish/English."""
    return max(1, len(text) // 4)


def select_by_budget(
    results: list[dict[str, Any]],
    budget: TokenBudgetConfig | None = None,
) -> list[dict[str, Any]]:
    """Greedily select highest-scored results until token budget is filled.
    
    Args:
        results: List of result dicts with at least {'text': str, ...}.
                 Should be pre-sorted by relevance (best first).
        budget: Token budget configuration.
    
    Returns:
        Subset of results that fit within the budget, truncated as needed.
    """
    cfg = budget or TokenBudgetConfig()
    
    # Compute combined score for each result
    for r in results:
        fusion = r.get("score", 0.0)
        relevance = r.get("relevance_score", 0.5)
        r["_combined_score"] = fusion * 0.7 + relevance * 0.3
    
    # Sort by combined score descending
    results = sorted(results, key=lambda x: x.get("_combined_score", 0.0), reverse=True)
    
    selected: list[dict[str, Any]] = []
    tokens_used = 0
    
    for r in results:
        text = r.get("text", "")
        if len(text) > cfg.truncate_to_chars:
            r["text"] = text[:cfg.truncate_to_chars]
            text = r["text"]
        
        needed = estimate_tokens(text)
        if tokens_used + needed > cfg.max_tokens:
            break
        selected.append(r)
        tokens_used += needed
        
        if len(selected) >= cfg.max_results:
            break
    
    return selected


def format_memories_for_prompt(
    results: list[dict[str, Any]],
    query: str = "",
) -> str:
    """Format memory results as a block for system prompt injection.
    
    Args:
        results: List of result dicts with keys:
                 - text: exchange/memory text
                 - source: 'memory' or 'session'
                 - source_key: identifier
                 - score: fusion score (float)
                 - entities: optional list of entity names
        query: Original query (for header).
    
    Returns:
        Formatted string block ready for system prompt.
    """
    if not results:
        return ""
    
    lines = [
        "\n--- 🔍 Retrieving relevant memories... ---",
        "The memories below were automatically retrieved based on the user's current message.",
        "They come from past sessions and curated memory. Treat them as context.",
        "",
    ]
    if query:
        lines.append(f"  (search: \"{query}\")\n")
    
    for i, r in enumerate(results, 1):
        score_pct = int(r.get("score", 0) * 100)
        text = r.get("text", "")
        source = r.get("source", "?")
        key = r.get("source_key", "")
        entities = r.get("entities", [])
        
        ent_str = ""
        if entities:
            ent_names = [e if isinstance(e, str) else e.get("name", "") for e in entities[:3]]
            ent_str = f" [entidades: {', '.join(ent_names)}]"
        
        rel_score = r.get("relevance_score", 0.5)
        lines.append(f"{i}. [{score_pct}%|rel:{rel_score:.2f}] {key}{ent_str}")
        lines.append(f"   {text}")
        lines.append("")
    
    return "\n".join(lines)
