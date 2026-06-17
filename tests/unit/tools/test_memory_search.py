import pytest
from unittest.mock import AsyncMock

from src.tools.memory_search import run as memory_search_run


@pytest.fixture
def mock_repos():
    memory_index = AsyncMock()
    memory_index.search = AsyncMock()
    memory_repos = AsyncMock()
    memory_repos.memory_index = memory_index
    repos = AsyncMock()
    repos.memory = memory_repos
    return repos


@pytest.mark.anyio
async def test_empty_query_returns_error():
    result = await memory_search_run(query="")
    assert result == "[ERROR] La búsqueda no puede estar vacía."


@pytest.mark.anyio
async def test_whitespace_query_returns_error():
    result = await memory_search_run(query="   ")
    assert result == "[ERROR] La búsqueda no puede estar vacía."


@pytest.mark.anyio
async def test_no_repos_returns_error():
    result = await memory_search_run(query="test", _repos=None)
    assert result == "[ERROR] Sistema de memoria no disponible."


@pytest.mark.anyio
async def test_repos_without_memory_returns_error():
    repos = AsyncMock()
    repos.memory = None
    result = await memory_search_run(query="test", _repos=repos)
    assert result == "[ERROR] Sistema de memoria no disponible."


@pytest.mark.anyio
async def test_search_raises_returns_error():
    repos = AsyncMock()
    mem = AsyncMock()
    mem.memory_index = AsyncMock()
    mem.memory_index.search = AsyncMock(side_effect=Exception("DB error"))
    repos.memory = mem

    result = await memory_search_run(query="test", _repos=repos)
    assert "[ERROR] Error al buscar en memoria: DB error" in result


@pytest.mark.anyio
async def test_no_results_returns_ok_message(mock_repos):
    mock_repos.memory.memory_index.search.return_value = []

    result = await memory_search_run(query="Mauro", _repos=mock_repos)
    assert result == "[OK] No se encontraron entradas en memoria para 'Mauro'."


@pytest.mark.anyio
async def test_returns_formatted_results(mock_repos):
    mock_repos.memory.memory_index.search.return_value = [
        {"key": "user:name", "value": "Mauro", "updated_at": "2024-01-01"},
        {"key": "user:lang", "value": "Python", "updated_at": ""},
    ]

    result = await memory_search_run(query="Mauro", _repos=mock_repos)

    assert "2 resultados" in result
    assert "user:name" in result
    assert "Mauro" in result
    assert "2024-01-01" in result
    assert "user:lang" in result
    assert "Python" in result


@pytest.mark.anyio
async def test_limit_is_applied(mock_repos):
    mock_repos.memory.memory_index.search.return_value = [
        {"key": f"k:{i}", "value": f"v{i}", "updated_at": ""}
        for i in range(30)
    ]

    result = await memory_search_run(query="k", _repos=mock_repos, limit=10)

    assert "10 resultados" in result


@pytest.mark.anyio
async def test_limit_capped_at_50(mock_repos):
    mock_repos.memory.memory_index.search.return_value = [
        {"key": f"k:{i}", "value": f"v{i}", "updated_at": ""}
        for i in range(100)
    ]

    result = await memory_search_run(query="k", _repos=mock_repos, limit=999)

    assert "50 resultados" in result


@pytest.mark.anyio
async def test_default_limit_is_20(mock_repos):
    mock_repos.memory.memory_index.search.return_value = [
        {"key": f"k:{i}", "value": f"v{i}", "updated_at": ""}
        for i in range(50)
    ]

    result = await memory_search_run(query="k", _repos=mock_repos)

    assert "20 resultados" in result


@pytest.mark.anyio
async def test_search_called_with_query(mock_repos):
    mock_repos.memory.memory_index.search.return_value = []

    await memory_search_run(query="buscar esto", _repos=mock_repos)

    mock_repos.memory.memory_index.search.assert_awaited_once_with("buscar esto")
