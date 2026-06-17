import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tools.search_entities import run, DEFINITION


class TestSearchEntitiesDefinition:
    def test_definition_structure(self):
        assert DEFINITION["type"] == "function"
        fdef = DEFINITION["function"]
        assert fdef["name"] == "search_entities"
        assert "query" in fdef["parameters"]["required"]
        props = fdef["parameters"]["properties"]
        assert "query" in props
        assert "entity_type" in props
        assert "limit" in props
        assert props["entity_type"]["default"] == ""
        assert props["limit"]["default"] == 10


class TestSearchEntitiesRun:
    @pytest.mark.anyio
    async def test_happy_path(self):
        mock_repo = AsyncMock()
        mock_repo.search_entities.return_value = [
            {"name": "Python", "entity_type": "lenguaje", "mention_count": 15, "last_seen": "2025-06-10T12:00:00"},
            {"name": "FastAPI", "entity_type": "tecnologia", "mention_count": 8, "last_seen": "2025-06-09T10:00:00"},
        ]
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(query="Python", _repos=_repos)

        mock_repo.search_entities.assert_awaited_once_with("Python", entity_type=None, limit=10)
        assert "Python" in result
        assert "lenguaje" in result
        assert "FastAPI" in result

    @pytest.mark.anyio
    async def test_empty_query_returns_error(self):
        result = await run(query="  ", _repos=None)
        assert "[ERROR]" in result
        assert "empty" in result.lower()

    @pytest.mark.anyio
    async def test_no_results(self):
        mock_repo = AsyncMock()
        mock_repo.search_entities.return_value = []
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(query="NonExistent", _repos=_repos)

        mock_repo.search_entities.assert_awaited_once()
        assert "No se encontraron" in result

    @pytest.mark.anyio
    async def test_filter_by_entity_type(self):
        mock_repo = AsyncMock()
        mock_repo.search_entities.return_value = [
            {"name": "Mau", "entity_type": "persona", "mention_count": 5, "last_seen": "2025-06-10T12:00:00"},
        ]
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(query="Mau", entity_type="persona", _repos=_repos)

        mock_repo.search_entities.assert_awaited_once_with("Mau", entity_type="persona", limit=10)
        assert "Mau" in result

    @pytest.mark.anyio
    async def test_limit_clamped_to_50(self):
        mock_repo = AsyncMock()
        mock_repo.search_entities.return_value = []
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        await run(query="test", limit=999, _repos=_repos)

        mock_repo.search_entities.assert_awaited_once_with("test", entity_type=None, limit=50)

    @pytest.mark.anyio
    async def test_error_from_repo_returns_error_message(self):
        mock_repo = AsyncMock()
        mock_repo.search_entities.side_effect = ValueError("DB connection lost")
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(query="test", _repos=_repos)

        assert "[ERROR]" in result
        assert "DB connection lost" in result

    @pytest.mark.anyio
    async def test_fallback_to_linker_when_no_repos(self, monkeypatch):
        async def fake_search(query, entity_type=None, limit=10):
            return [{"name": "Fallback", "entity_type": "tema", "mention_count": 1, "last_seen": "2025-01-01"}]
        monkeypatch.setattr("src.memory.entity.linker.search_entities", fake_search)

        result = await run(query="Fallback", _repos=None)

        assert "Fallback" in result

    @pytest.mark.anyio
    async def test_fallback_when_entity_graph_is_none(self, monkeypatch):
        async def fake_search(query, entity_type=None, limit=10):
            return [{"name": "DirectFallback", "entity_type": "tema", "mention_count": 1, "last_seen": "2025-01-01"}]
        monkeypatch.setattr("src.memory.entity.linker.search_entities", fake_search)

        _repos = MagicMock()
        _repos.memory.entity_graph = None
        result = await run(query="DirectFallback", _repos=_repos)

        assert "DirectFallback" in result
