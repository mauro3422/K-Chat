import pytest
from unittest.mock import AsyncMock

from src.tools.list_memories import run as list_memories_run


@pytest.fixture
def mock_repos():
    memory_index = AsyncMock()
    memory_index.get_all = AsyncMock()
    memory_repos = AsyncMock()
    memory_repos.memory_index = memory_index
    repos = AsyncMock()
    repos.memory = memory_repos
    return repos


@pytest.mark.anyio
async def test_list_memories_no_repos_returns_error():
    result = await list_memories_run(_repos=None)
    assert result == "[ERROR] Sistema de memoria no disponible."


@pytest.mark.anyio
async def test_list_memories_repos_without_memory_returns_error():
    repos = AsyncMock()
    repos.memory = None
    result = await list_memories_run(_repos=repos)
    assert result == "[ERROR] Sistema de memoria no disponible."


@pytest.mark.anyio
async def test_list_memories_get_all_raises_returns_error():
    repos = AsyncMock()
    mem = AsyncMock()
    mem.memory_index = AsyncMock()
    mem.memory_index.get_all = AsyncMock(side_effect=Exception("DB error"))
    repos.memory = mem

    result = await list_memories_run(_repos=repos)
    assert "[ERROR] Error al leer memoria: DB error" in result


@pytest.mark.anyio
async def test_list_memories_empty(mock_repos):
    mock_repos.memory.memory_index.get_all.return_value = []

    result = await list_memories_run(_repos=mock_repos)
    assert "[OK] No hay entradas en memoria todavía." in result


@pytest.mark.anyio
async def test_list_memories_returns_all_grouped(mock_repos):
    mock_repos.memory.memory_index.get_all.return_value = [
        {"key": "user:name", "value": "Mauro"},
        {"key": "user:lang", "value": "Python"},
        {"key": "proyecto:nombre", "value": "K-Chat"},
    ]

    result = await list_memories_run(_repos=mock_repos)

    assert "3 entradas" in result
    assert "**proyecto**" in result
    assert "**user**" in result
    assert "`user:name` → Mauro" in result
    assert "`user:lang` → Python" in result
    assert "`proyecto:nombre` → K-Chat" in result


@pytest.mark.anyio
async def test_list_memories_filters_by_prefix(mock_repos):
    mock_repos.memory.memory_index.get_all.return_value = [
        {"key": "user:name", "value": "Mauro"},
        {"key": "user:lang", "value": "Python"},
        {"key": "proyecto:nombre", "value": "K-Chat"},
    ]

    result = await list_memories_run(_repos=mock_repos, prefix="user:")

    assert "2 entradas" in result
    assert "filtro: 'user:'" in result
    assert "`user:name`" in result
    assert "`user:lang`" in result
    assert "proyecto" not in result


@pytest.mark.anyio
async def test_list_memories_prefix_no_match(mock_repos):
    mock_repos.memory.memory_index.get_all.return_value = [
        {"key": "user:name", "value": "Mauro"},
    ]

    result = await list_memories_run(_repos=mock_repos, prefix="bug:")

    assert "[OK] No se encontraron entradas con prefijo 'bug:'." in result


@pytest.mark.anyio
async def test_list_memories_truncates_long_values(mock_repos):
    long_value = "a" * 200
    mock_repos.memory.memory_index.get_all.return_value = [
        {"key": "user:bio", "value": long_value},
    ]

    result = await list_memories_run(_repos=mock_repos)

    assert "`user:bio` →" in result
    assert ("a" * 97) + "..." in result
