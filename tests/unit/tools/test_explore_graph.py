import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tools.explore_graph import run, DEFINITION


class TestExploreGraphDefinition:
    def test_definition_structure(self):
        assert DEFINITION["type"] == "function"
        fdef = DEFINITION["function"]
        assert fdef["name"] == "explore_graph"
        assert "entity_id" in fdef["parameters"]["required"]
        props = fdef["parameters"]["properties"]
        assert "entity_id" in props
        assert "depth" in props
        assert props["depth"]["default"] == 2


class TestExploreGraphRun:
    @pytest.mark.anyio
    async def test_happy_path(self):
        mock_repo = AsyncMock()
        mock_repo.explore_graph.return_value = [
            {"id": "e2", "name": "FastAPI", "entity_type": "tecnologia", "relation_type": "usa", "depth": 1},
            {"id": "e3", "name": "Python", "entity_type": "lenguaje", "relation_type": "co_occurrence", "depth": 2},
        ]
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(entity_id="e1", _repos=_repos)

        mock_repo.explore_graph.assert_awaited_once_with("e1", depth=2)
        assert "FastAPI" in result
        assert "Python" in result
        assert "Graph Explorer" in result

    @pytest.mark.anyio
    async def test_empty_entity_id_returns_error(self):
        result = await run(entity_id="  ", _repos=None)
        assert "[ERROR]" in result
        assert "empty" in result.lower()

    @pytest.mark.anyio
    async def test_entity_found_but_no_connections(self):
        mock_repo = AsyncMock()
        mock_repo.explore_graph.return_value = []
        mock_repo.get_entity.return_value = {"id": "e1", "name": "MiEntity", "entity_type": "tema"}
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(entity_id="e1", _repos=_repos)

        mock_repo.get_entity.assert_awaited_once_with("e1")
        assert "MiEntity" in result
        assert "sin conexiones" in result

    @pytest.mark.anyio
    async def test_entity_not_found(self):
        mock_repo = AsyncMock()
        mock_repo.explore_graph.return_value = []
        mock_repo.get_entity.return_value = None
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(entity_id="nonexistent_id_123", _repos=_repos)

        assert "No se encontró" in result
        assert "nonexistent" in result

    @pytest.mark.anyio
    async def test_depth_clamped_to_5(self):
        mock_repo = AsyncMock()
        mock_repo.explore_graph.return_value = []
        mock_repo.get_entity.return_value = None
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        await run(entity_id="e1", depth=999, _repos=_repos)

        mock_repo.explore_graph.assert_awaited_once_with("e1", depth=5)

    @pytest.mark.anyio
    async def test_error_from_repo_returns_error_message(self):
        mock_repo = AsyncMock()
        mock_repo.explore_graph.side_effect = RuntimeError("graph crashed")
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(entity_id="e1", _repos=_repos)

        assert "[ERROR]" in result
        assert "graph crashed" in result

    @pytest.mark.anyio
    async def test_truncates_more_than_10_per_depth(self):
        mock_repo = AsyncMock()
        items = [
            {"id": f"e{i}", "name": f"Entity{i}", "entity_type": "tema", "relation_type": "co_occurrence", "depth": 1}
            for i in range(15)
        ]
        mock_repo.explore_graph.return_value = items
        _repos = MagicMock()
        _repos.memory.entity_graph = mock_repo

        result = await run(entity_id="root", _repos=_repos)

        assert "... y 5 más" in result
        for i in range(10):
            assert f"Entity{i}" in result

    @pytest.mark.anyio
    async def test_fallback_to_linker_when_no_repos(self, monkeypatch):
        async def fake_explore(entity_id, depth=2):
            return [
                {"id": "e2", "name": "LinkedEntity", "entity_type": "tema", "relation_type": "co_occurrence", "depth": 1},
            ]
        monkeypatch.setattr("src.memory.entity.linker.explore_graph", fake_explore)

        result = await run(entity_id="e1", _repos=None)

        assert "LinkedEntity" in result

    @pytest.mark.anyio
    async def test_fallback_when_entity_graph_is_none(self, monkeypatch):
        async def fake_explore(entity_id, depth=2):
            return [
                {"id": "e2", "name": "DirectLinked", "entity_type": "tema", "relation_type": "co_occurrence", "depth": 1},
            ]
        monkeypatch.setattr("src.memory.entity.linker.explore_graph", fake_explore)

        _repos = MagicMock()
        _repos.memory.entity_graph = None
        result = await run(entity_id="e1", _repos=_repos)

        assert "DirectLinked" in result

    @pytest.mark.anyio
    async def test_fallback_explore_graph_returns_no_results_and_no_entity(self, monkeypatch):
        async def fake_explore(entity_id, depth=2):
            return []
        monkeypatch.setattr("src.memory.entity.linker.explore_graph", fake_explore)

        result = await run(entity_id="missing_entity_123", _repos=None)
        assert "No se encontró" in result
