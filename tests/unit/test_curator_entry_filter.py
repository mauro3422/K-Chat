from src.memory.curator.entry_filter import (
    curator_entries_are_duplicates,
    curator_entry_similarity,
    filter_curator_entries,
    has_allowed_curator_category,
    is_trivial_curator_entry,
)


def test_trivial_name_entries_are_rejected():
    assert is_trivial_curator_entry(
        {"key": "user:name", "value": "2026-07-09 20:30 | Mauro"}
    )


def test_exact_key_duplicate_keeps_more_informative_value():
    entries, stats = filter_curator_entries(
        [
            {
                "key": "bug:get-tool-history-async-error",
                "value": "2026-07-09 20:30 | Falta await.",
            },
            {
                "key": "bug:get-tool-history-async-error",
                "value": (
                    "2026-07-09 20:31 | get_tool_history llama una función async "
                    "sin await y pierde la coroutine."
                ),
            },
        ]
    )

    assert len(entries) == 1
    assert "pierde la coroutine" in entries[0]["value"]
    assert stats == {"input": 2, "kept": 1, "trivial": 0, "invalid_category": 0, "duplicates": 1}


def test_semantic_duplicate_with_different_key_is_collapsed():
    first = {
        "key": "bug:async-history-call",
        "value": "2026-07-09 20:30 | get_tool_history llama async sin await y pierde la coroutine",
    }
    second = {
        "key": "bug:history-coroutine-not-awaited",
        "value": "2026-07-09 20:31 | get_tool_history llama async sin await; la coroutine se pierde",
    }

    assert curator_entry_similarity(first, second) >= 0.72
    entries, stats = filter_curator_entries([first, second])
    assert len(entries) == 1
    assert stats["duplicates"] == 1


def test_same_wording_in_different_categories_is_preserved():
    entries, stats = filter_curator_entries(
        [
            {
                "key": "bug:memory-threshold",
                "value": "2026-07-09 20:30 | Mantener inyección automática hasta superar el umbral",
            },
            {
                "key": "decision:memory-threshold",
                "value": "2026-07-09 20:30 | Mantener inyección automática hasta superar el umbral",
            },
        ]
    )

    assert len(entries) == 2
    assert stats["duplicates"] == 0
    assert not curator_entries_are_duplicates(entries[0], entries[1])


def test_unknown_category_is_rejected() -> None:
    entries, stats = filter_curator_entries(
        [{"key": "request:fix-db-query", "value": "2026-07-10 12:06 | Investigar el flujo."}]
    )

    assert entries == []
    assert stats["invalid_category"] == 1
    assert not has_allowed_curator_category({"key": "request:fix-db-query"})


def test_generated_user_name_variant_is_trivial() -> None:
    entries, stats = filter_curator_entries([
        {"key": "user:user-name-mauro", "value": "2026-07-10 12:06 | Mauro"},
        {"key": "user:name-mauro", "value": "2026-07-10 12:06 | Mauro"},
    ])

    assert entries == []
    assert stats["trivial"] == 2
