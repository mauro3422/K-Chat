import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tools.recall_memories import run as recall_memories_run
from src.memory.retrieval.hybrid_retriever import HybridResult


def make_result(
    text: str,
    fusion_score: float = 0.8,
    rank: int = 1,
    source: str = "memory",
    vector_score: float = 0.7,
    keyword_score: float = 0.5,
    entity_score: float = 0.3,
    source_key: str = "",
) -> HybridResult:
    return HybridResult(
        rowid=rank,
        text=text,
        fusion_score=fusion_score,
        rank=rank,
        source=source,
        vector_score=vector_score,
        keyword_score=keyword_score,
        entity_score=entity_score,
        source_key=source_key,
    )


@pytest.fixture
def mock_repos():
    retriever = AsyncMock()
    retriever.search = AsyncMock()
    memory_repos = AsyncMock()
    memory_repos.hybrid_retriever = retriever
    repos = AsyncMock()
    repos.memory = memory_repos
    return repos


@pytest.mark.anyio
async def test_empty_query_returns_error():
    result = await recall_memories_run(query="")
    assert result == "[ERROR] query cannot be empty."


@pytest.mark.anyio
async def test_whitespace_query_returns_error():
    result = await recall_memories_run(query="   ")
    assert result == "[ERROR] query cannot be empty."


@pytest.mark.anyio
async def test_no_repos_uses_fallback(mock_repos):
    with patch(
        "src.tools.recall_memories._fallback_vector_search",
        new_callable=AsyncMock,
        return_value="[fallback] result",
    ) as mock_fallback:
        result = await recall_memories_run(query="test", _repos=None)

        mock_fallback.assert_awaited_once()
        assert result == "[fallback] result"


@pytest.mark.anyio
async def test_no_hybrid_retriever_falls_back(mock_repos):
    repos = AsyncMock()
    repos.memory = AsyncMock()
    repos.memory.hybrid_retriever = None

    with patch(
        "src.tools.recall_memories._fallback_vector_search",
        new_callable=AsyncMock,
        return_value="[fallback] result",
    ) as mock_fallback:
        result = await recall_memories_run(query="test", _repos=repos)

        mock_fallback.assert_awaited_once()
        assert result == "[fallback] result"


@pytest.mark.anyio
async def test_search_raises_returns_error(mock_repos):
    mock_repos.memory.hybrid_retriever.search = AsyncMock(
        side_effect=Exception("search failed")
    )

    result = await recall_memories_run(query="test", _repos=mock_repos)

    assert "[ERROR] Failed to search memories: search failed" in result


@pytest.mark.anyio
async def test_no_results_after_min_score(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(text="low score", fusion_score=0.1),
    ]

    result = await recall_memories_run(query="test", _repos=mock_repos)

    assert "No se encontraron recuerdos" in result


@pytest.mark.anyio
async def test_returns_formatted_results(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(
            text="Mauro lives in Argentina",
            fusion_score=0.9,
            rank=1,
            source="memory",
            vector_score=0.85,
            keyword_score=0.6,
            entity_score=0.4,
            source_key="user:location",
        ),
        make_result(
            text="Chat about Python",
            fusion_score=0.75,
            rank=2,
            source="session",
            vector_score=0.7,
            keyword_score=0.0,
            entity_score=0.0,
        ),
    ]

    result = await recall_memories_run(query="Mauro", _repos=mock_repos)

    assert "Resultados" in result
    assert "Mauro lives in Argentina" in result
    assert "Chat about Python" in result
    assert "user:location" in result
    assert "vec85%" in result
    assert "kw60" in result
    assert "2 resultados" in result


@pytest.mark.anyio
async def test_limit_is_applied(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(text=f"result {i}", fusion_score=0.9, rank=i)
        for i in range(10)
    ]

    result = await recall_memories_run(query="test", _repos=mock_repos, limit=3)

    lines = result.strip().split("\n")
    displayed_items = [l for l in lines if l.strip() and l.strip()[0].isdigit()]
    assert len(displayed_items) == 3


@pytest.mark.anyio
async def test_limit_capped_at_20(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(text=f"result {i}", fusion_score=0.9, rank=i)
        for i in range(50)
    ]

    result = await recall_memories_run(query="test", _repos=mock_repos, limit=999)

    lines = result.strip().split("\n")
    displayed_items = [l for l in lines if l.strip() and l.strip()[0].isdigit()]
    assert len(displayed_items) == 20


@pytest.mark.anyio
async def test_default_limit_is_5(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(text=f"result {i}", fusion_score=0.9, rank=i)
        for i in range(10)
    ]

    result = await recall_memories_run(query="test", _repos=mock_repos)

    lines = result.strip().split("\n")
    displayed_items = [l for l in lines if l.strip() and l.strip()[0].isdigit()]
    assert len(displayed_items) == 5


@pytest.mark.anyio
async def test_min_score_filters_low_scores(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(text="high", fusion_score=0.8, rank=1),
        make_result(text="medium", fusion_score=0.5, rank=2),
        make_result(text="low", fusion_score=0.2, rank=3),
    ]

    result = await recall_memories_run(
        query="test", _repos=mock_repos, min_score=0.6
    )

    assert "high" in result
    assert "medium" not in result
    assert "low" not in result


@pytest.mark.anyio
async def test_passes_source_filter(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = []

    await recall_memories_run(
        query="test", _repos=mock_repos, source="memory"
    )

    mock_repos.memory.hybrid_retriever.search.assert_awaited_once_with(
        query="test", top_k=10, source_filter="memory"
    )


@pytest.mark.anyio
async def test_empty_source_passes_none_filter(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = []

    await recall_memories_run(query="test", _repos=mock_repos, source="")

    mock_repos.memory.hybrid_retriever.search.assert_awaited_once_with(
        query="test", top_k=10, source_filter=None
    )


@pytest.mark.anyio
async def test_signal_breakdown_omitted_when_below_threshold(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = [
        make_result(
            text="test",
            fusion_score=0.8,
            rank=1,
            vector_score=0.2,
            keyword_score=0.0,
            entity_score=0.0,
        ),
    ]

    result = await recall_memories_run(query="test", _repos=mock_repos)

    assert "[vec" not in result
    assert "[kw" not in result
    assert "[ent" not in result


@pytest.mark.anyio
async def test_uses_top_k_limit_x2(mock_repos):
    mock_repos.memory.hybrid_retriever.search.return_value = []

    await recall_memories_run(query="test", _repos=mock_repos, limit=7)

    mock_repos.memory.hybrid_retriever.search.assert_awaited_once_with(
        query="test", top_k=14, source_filter=None
    )
