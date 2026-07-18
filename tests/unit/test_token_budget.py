"""Tests for token_budget: estimate_tokens, select_by_budget, format_memories_for_prompt."""

from __future__ import annotations

import pytest

from src.memory.retrieval.token_budget import (
    TokenBudgetConfig,
    estimate_tokens,
    format_memories_for_prompt,
    select_by_budget,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def a_result() -> dict:
    return {"text": "short text", "score": 0.9, "source": "memory", "source_key": "mem_1"}


@pytest.fixture
def several_results() -> list[dict]:
    return [
        {"text": "alpha", "score": 0.9, "relevance_score": 0.8, "source": "memory", "source_key": "mem_a"},
        {"text": "beta", "score": 0.5, "relevance_score": 0.6, "source": "session", "source_key": "sess_b"},
        {"text": "gamma", "score": 0.3, "relevance_score": 0.4, "source": "memory", "source_key": "mem_c"},
    ]


# ===================================================================
# estimate_tokens
# ===================================================================

class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 1

    def test_very_short(self):
        assert estimate_tokens("hi") == 1

    def test_exactly_one_token(self):
        assert estimate_tokens("abcd") == 1

    def test_short_text(self):
        assert estimate_tokens("hello world") == 2

    def test_long_text(self):
        text = "a" * 4000
        assert estimate_tokens(text) == 1000

    def test_spanish_text(self):
        text = "Hola, ¿cómo estás? Todo bien por aquí, trabajando en el proyecto."
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert estimate_tokens("éáíóúñü") == 1


# ===================================================================
# select_by_budget
# ===================================================================

class TestSelectByBudget:
    def test_empty_list(self):
        assert select_by_budget([]) == []

    def test_single_result_fits(self, a_result):
        result = select_by_budget([a_result])
        assert len(result) == 1
        assert result[0]["text"] == "short text"

    def test_multiple_results_sorted_by_combined_score(self, several_results):
        results = select_by_budget(several_results)
        assert len(results) == 3
        scores = [r["_combined_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_combined_score_formula(self):
        results = [{"text": "x", "score": 0.96, "relevance_score": 0.0}]
        selected = select_by_budget(results)
        assert selected[0]["_combined_score"] == pytest.approx(0.96 * 0.7 + 0.0 * 0.3)

    def test_budget_cap_stops_when_full(self):
        results = [
            {"text": "x", "score": 1.0, "source": "m", "source_key": "k1"},
            {"text": "y", "score": 0.9, "source": "m", "source_key": "k2"},
            {"text": "z" * 400, "score": 0.8, "source": "m", "source_key": "k3"},
        ]
        cfg = TokenBudgetConfig(max_tokens=5, per_result_tokens=200, max_results=15, truncate_to_chars=300)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected) <= 2
        tokens_used = sum(estimate_tokens(r.get("text", "")) for r in selected)
        assert tokens_used <= cfg.max_tokens

    def test_per_result_tokens_truncation(self):
        long = "a" * 500
        results = [{"text": long, "score": 1.0, "source": "m", "source_key": "k"}]
        cfg = TokenBudgetConfig(truncate_to_chars=50, max_tokens=5000)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected[0]["text"]) == 50

    def test_max_results_hard_limit(self):
        results = [{"text": "x", "score": 1.0, "source": "m", "source_key": f"k{i}"} for i in range(100)]
        cfg = TokenBudgetConfig(max_results=3, max_tokens=5000)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected) == 3

    def test_missing_text_field(self):
        results = [{"score": 0.9, "source": "m", "source_key": "k"}]
        selected = select_by_budget(results)
        assert len(selected) == 1
        assert selected[0].get("text", "") == ""

    def test_missing_score_field(self):
        results = [{"text": "hello", "relevance_score": 0.7, "source": "m", "source_key": "k"}]
        selected = select_by_budget(results)
        assert selected[0]["_combined_score"] == pytest.approx(0.0 * 0.7 + 0.7 * 0.3)

    def test_custom_token_budget_config(self):
        results = [
            {"text": "a", "score": 1.0, "source": "m", "source_key": "k1"},
            {"text": "b", "score": 0.8, "source": "m", "source_key": "k2"},
        ]
        cfg = TokenBudgetConfig(max_tokens=1, per_result_tokens=200, max_results=15, truncate_to_chars=300)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected) <= 1

    def test_results_prefer_higher_combined_score(self):
        results = [
            {"text": "low", "score": 0.1, "source": "m", "source_key": "k1"},
            {"text": "high", "score": 0.9, "source": "m", "source_key": "k2"},
        ]
        selected = select_by_budget(results)
        assert selected[0]["source_key"] == "k2"

    def test_relevance_score_defaults_to_0_5(self):
        results = [{"text": "x", "score": 0.0, "source": "m", "source_key": "k"}]
        selected = select_by_budget(results)
        assert selected[0]["_combined_score"] == pytest.approx(0.0 * 0.7 + 0.5 * 0.3)

    def test_score_zero_but_relevance_score_exists(self):
        results = [{"text": "x", "score": 0.0, "relevance_score": 1.0, "source": "m", "source_key": "k"}]
        selected = select_by_budget(results)
        assert selected[0]["_combined_score"] == pytest.approx(0.0 * 0.7 + 1.0 * 0.3)


# ===================================================================
# format_memories_for_prompt
# ===================================================================

class TestFormatMemoriesForPrompt:
    def test_empty_results_returns_empty_string(self):
        assert format_memories_for_prompt([]) == ""

    def test_single_result_formatting(self, a_result):
        output = format_memories_for_prompt([a_result])
        assert "short text" in output
        assert "90%" in output
        assert "mem_1" in output
        assert "🔍" in output

    def test_multiple_results_with_scores(self, several_results):
        output = format_memories_for_prompt(several_results)
        lines = output.strip().split("\n")
        assert "90%" in output
        assert "50%" in output
        assert "30%" in output
        assert "mem_a" in output
        assert "sess_b" in output
        assert "mem_c" in output

    def test_with_query(self, a_result):
        output = format_memories_for_prompt([a_result], query="hello")
        assert "search" in output
        assert "hello" in output

    def test_without_query(self, a_result):
        output = format_memories_for_prompt([a_result])
        assert "búsqueda" not in output

    def test_score_rounding_zero(self):
        results = [{"text": "x", "score": 0.0, "source": "m", "source_key": "k"}]
        output = format_memories_for_prompt(results)
        assert "0%" in output

    def test_score_rounding_0999(self):
        results = [{"text": "x", "score": 0.999, "source": "m", "source_key": "k"}]
        output = format_memories_for_prompt(results)
        assert "99%" in output

    def test_score_rounding_one(self):
        results = [{"text": "x", "score": 1.0, "source": "m", "source_key": "k"}]
        output = format_memories_for_prompt(results)
        assert "100%" in output

    def test_entities_as_strings(self):
        results = [{"text": "x", "score": 0.5, "source": "m", "source_key": "k", "entities": ["foo", "bar"]}]
        output = format_memories_for_prompt(results)
        assert "foo" in output
        assert "bar" in output
        assert "entidades" in output

    def test_entities_as_dicts(self):
        results = [{"text": "x", "score": 0.5, "source": "m", "source_key": "k", "entities": [{"name": "foo"}, {"name": "bar"}]}]
        output = format_memories_for_prompt(results)
        assert "foo" in output
        assert "bar" in output

    def test_entities_more_than_three_only_shows_first_three(self):
        results = [{"text": "x", "score": 0.5, "source": "m", "source_key": "k", "entities": ["a", "b", "c", "d"]}]
        output = format_memories_for_prompt(results)
        assert "entidades: a, b, c" in output
        assert "a, b, c, d" not in output

    def test_empty_entities_list(self, a_result):
        output = format_memories_for_prompt([a_result])
        assert "entidades" not in output

    def test_truncation_not_done_in_format(self):
        long = "a" * 1000
        results = [{"text": long, "score": 0.5, "source": "m", "source_key": "k"}]
        output = format_memories_for_prompt(results)
        assert len(output) > 200
        assert long in output

    def test_format_includes_relevance_score(self, a_result):
        output = format_memories_for_prompt([a_result])
        assert "rel:" in output

    def test_format_includes_receipt_handle_when_present(self):
        output = format_memories_for_prompt(
            [
                {
                    "text": "contexto caliente",
                    "score": 0.8,
                    "source": "memory",
                    "source_key": "user:workflow",
                    "receipt_id": "mr_123",
                }
            ]
        )

        assert "[receipt:mr_123]" in output

    def test_relevance_score_default_formatting(self):
        results = [{"text": "x", "score": 0.5, "source": "m", "source_key": "k"}]
        output = format_memories_for_prompt(results)
        assert "rel:0.50" in output


# ===================================================================
# Combined: select_by_budget + format_memories_for_prompt roundtrip
# ===================================================================

class TestCombinedRoundtrip:
    def test_select_then_format(self, several_results):
        selected = select_by_budget(several_results)
        assert len(selected) > 0
        output = format_memories_for_prompt(selected)
        assert "alpha" in output
        assert "beta" in output
        assert "gamma" in output

    def test_select_large_truncation_then_format(self):
        results = [{"text": "x" * 2000, "score": 0.9, "source": "m", "source_key": "k"}]
        cfg = TokenBudgetConfig(truncate_to_chars=10, max_results=5)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected[0]["text"]) == 10
        output = format_memories_for_prompt(selected)
        assert selected[0]["text"] in output

    def test_select_non_default_budget_then_format(self):
        results = [
            {"text": "one", "score": 0.9, "source": "m", "source_key": "k1"},
            {"text": "two", "score": 0.8, "source": "m", "source_key": "k2"},
            {"text": "three", "score": 0.7, "source": "m", "source_key": "k3"},
        ]
        cfg = TokenBudgetConfig(max_tokens=2, max_results=2)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected) <= 2
        output = format_memories_for_prompt(selected)
        assert output.startswith("\n") or output != ""
        assert "k1" in output
        if len(selected) > 1:
            assert "k2" in output


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    def test_results_with_empty_text(self):
        results = [{"text": "", "score": 0.9, "source": "m", "source_key": "k"}]
        selected = select_by_budget(results)
        assert len(selected) == 1
        output = format_memories_for_prompt(selected)
        assert "k" in output

    def test_score_zero_but_relevance_score_high(self):
        results = [{"text": "important", "score": 0.0, "relevance_score": 1.0, "source": "m", "source_key": "k"}]
        selected = select_by_budget(results)
        assert len(selected) == 1
        assert selected[0]["_combined_score"] == pytest.approx(0.3)
        output = format_memories_for_prompt(selected)
        assert "0%" in output
        assert "rel:1.00" in output

    def test_very_large_number_of_results(self):
        results = [{"text": "x", "score": 0.5, "source": "m", "source_key": f"k{i}"} for i in range(1000)]
        cfg = TokenBudgetConfig(max_tokens=50, max_results=1000)
        selected = select_by_budget(results, budget=cfg)
        assert len(selected) <= 200
        assert all(r["_combined_score"] == pytest.approx(0.5 * 0.7 + 0.5 * 0.3) for r in selected)

    def test_all_scores_zero(self):
        results = [{"text": "x", "score": 0.0, "source": "m", "source_key": f"k{i}"} for i in range(5)]
        selected = select_by_budget(results)
        assert len(selected) == 5

    def test_negative_scores(self):
        results = [{"text": "x", "score": -1.0, "source": "m", "source_key": "k1"}]
        selected = select_by_budget(results)
        assert len(selected) == 1
        assert selected[0]["_combined_score"] < 0
