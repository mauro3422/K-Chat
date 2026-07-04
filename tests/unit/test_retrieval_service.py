"""Tests for RetrievalService — throttling, retrieval, and auto-retrieval flow."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.services.retrieval_service import RetrievalService


class FakeGraphRepo:
    def __init__(self):
        self.lookups = []
        self.explored = []

    async def list_curated_relations_for_node(self, node_id: str, limit: int = 20):
        self.lookups.append((node_id, limit))
        if node_id != "memory:user:lenguaje":
            return []
        return [
            {
                "source_id": "candidate:cand-1",
                "target_id": "memory:user:lenguaje",
                "relation_type": "REFINES",
                "weight": 0.8,
                "evidence": "Mauro refined the memory recall protocol.",
            }
        ]

    async def explore_graph(self, node_id: str, depth: int = 1):
        self.explored.append((node_id, depth))
        return []

    async def search_entities(self, query: str, limit: int = 10):
        return []


class TestCheckThrottle:
    """Unit tests for _check_throttle — synchronous, no mocks needed."""

    def test_empty_message_returns_false(self):
        service = RetrievalService()
        assert service._check_throttle("s1", "") is False
        assert service._check_throttle("s1", "   ") is False
        assert service._check_throttle("s1", None) is False

    def test_short_message_returns_false(self):
        service = RetrievalService()
        assert service._check_throttle("s1", "ab") is False

    def test_first_turn_returns_true(self):
        service = RetrievalService()
        assert service._check_throttle("s1", "hello") is True

    def test_all_messages_pass_throttle_with_interval_1(self):
        service = RetrievalService()
        assert service._check_throttle("s1", "hello") is True
        assert service._check_throttle("s1", "hello") is True
        assert service._check_throttle("s1", "hello") is True

    def test_lru_eviction(self):
        service = RetrievalService()
        small_max = 5
        original_max = service.MAX_SESSIONS
        service.MAX_SESSIONS = small_max
        try:
            for i in range(small_max):
                assert service._check_throttle(f"session_{i}", "hello") is True

            assert len(service._throttle) == small_max

            assert service._check_throttle("new_session", "hello") is True
            assert len(service._throttle) == small_max
            assert "session_0" not in service._throttle
        finally:
            service.MAX_SESSIONS = original_max


class TestRetrieve:
    """Unit tests for retrieve() — async, mocked retriever."""

    @pytest.mark.anyio
    async def test_returns_none_false_when_retriever_none(self):
        with patch(
            "src.memory.retrieval.hybrid_retriever.HybridRetriever",
            return_value=None,
        ):
            service = RetrievalService()
            result = await service.retrieve("hello", db_path=":memory:")
            assert result == (None, False)

    @pytest.mark.anyio
    async def test_returns_memory_block_on_success(self):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"text": "test", "score": 0.5}

        mock_retriever = MagicMock()
        mock_retriever.search = AsyncMock(return_value=[mock_result])
        mock_retriever.was_reranker_degraded = False

        service = RetrievalService(retrieval_service=mock_retriever)

        with patch(
            "src.core.services.retrieval_service.format_memories_for_prompt",
            return_value="memory_block",
        ):
            result = await service.retrieve("hello")

        assert result == ("memory_block", False)
        mock_retriever.search.assert_awaited_once_with(
            "hello",
            top_k=8,
            apply_budget=True,
            source_filter="session",
            session_id="",
        )

    @pytest.mark.anyio
    async def test_explicit_recall_searches_across_sources_and_records_event(self, tmp_path):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"text": "memoria previa", "score": 0.7}

        mock_retriever = MagicMock()
        mock_retriever.search = AsyncMock(return_value=[mock_result])
        mock_retriever.was_reranker_degraded = False

        service = RetrievalService(
            retrieval_service=mock_retriever,
            recall_event_root=str(tmp_path),
        )

        with patch(
            "src.core.services.retrieval_service.format_memories_for_prompt",
            return_value="memory_block",
        ):
            result = await service.retrieve_if_allowed(
                "te acordas de Kairos memoria?",
                session_id="sess-1",
                config=MagicMock(auto_retrieval_enabled=True),
            )

        assert result == ("memory_block", False)
        mock_retriever.search.assert_awaited_once_with(
            "te acordas de Kairos memoria?",
            top_k=10,
            apply_budget=True,
            source_filter=None,
            session_id="sess-1",
        )
        artifacts = list((tmp_path / "memory" / "recall").rglob("*.jsonl"))
        assert len(artifacts) == 1
        assert "explicit_recall" in artifacts[0].read_text(encoding="utf-8")

    @pytest.mark.anyio
    async def test_explicit_recall_appends_curated_graph_context(self):
        mock_result = MagicMock()
        mock_result.text = "Mauro quiere recall transversal"
        mock_result.source = "memory"
        mock_result.source_key = "user:lenguaje"
        mock_result.to_dict.return_value = {
            "text": "Mauro quiere recall transversal",
            "score": 0.7,
            "source": "memory",
            "source_key": "user:lenguaje",
        }

        mock_retriever = MagicMock()
        mock_retriever.search = AsyncMock(return_value=[mock_result])
        mock_retriever.was_reranker_degraded = False
        graph = FakeGraphRepo()

        service = RetrievalService(
            retrieval_service=mock_retriever,
            entity_graph_repo=graph,
            record_recall_events=False,
        )

        memory_block, degraded = await service.retrieve_if_allowed(
            "te acordas de la memoria transversal?",
            session_id="sess-1",
            config=MagicMock(auto_retrieval_enabled=True),
        )

        assert degraded is False
        assert memory_block is not None
        assert "## Graph context" in memory_block
        assert "user:lenguaje -> cand-1 [curated:REFINES] weight=0.8" in memory_block
        assert graph.lookups == [("memory:user:lenguaje", 5)]

    @pytest.mark.anyio
    async def test_returns_none_true_when_reranker_degraded(self):
        mock_retriever = MagicMock()
        mock_retriever.search = AsyncMock(return_value=[])
        mock_retriever.was_reranker_degraded = True

        service = RetrievalService(retrieval_service=mock_retriever)
        result = await service.retrieve("hello")

        assert result == (None, True)

    @pytest.mark.anyio
    async def test_closes_retriever_after_use(self):
        mock_retriever = MagicMock()
        mock_retriever.search = AsyncMock(return_value=[])
        mock_retriever.was_reranker_degraded = False

        service = RetrievalService(retrieval_service=mock_retriever)
        await service.retrieve("hello")

        mock_retriever.close.assert_called_once()

    @pytest.mark.anyio
    async def test_handles_search_exception_gracefully(self):
        mock_retriever = MagicMock()
        mock_retriever.search = AsyncMock(side_effect=RuntimeError("db fail"))

        service = RetrievalService(retrieval_service=mock_retriever)
        result = await service.retrieve("hello")

        assert result == (None, True)


class TestRetrieveIfAllowed:
    """Unit tests for retrieve_if_allowed() — config + throttle gates."""

    @pytest.mark.anyio
    async def test_returns_none_false_when_auto_retrieval_disabled(self):
        config = MagicMock(auto_retrieval_enabled=False)
        service = RetrievalService()
        result = await service.retrieve_if_allowed("hello", config=config)
        assert result == (None, False)

    @pytest.mark.anyio
    @pytest.mark.anyio
    async def test_retrieval_runs_on_every_message_when_interval_1(self):
        """With RETRIEVAL_INTERVAL=1, every non-empty message triggers retrieval."""
        config = MagicMock(auto_retrieval_enabled=True)
        service = RetrievalService()

        with patch.object(service, "retrieve", return_value=("mem", False)):
            r1 = await service.retrieve_if_allowed("hello", session_id="s1", config=config)
            assert r1 == ("mem", False)

            r2 = await service.retrieve_if_allowed("hello", session_id="s1", config=config)
            assert r2 == ("mem", False)  # No longer throttled — runs every turn
    @pytest.mark.anyio
    async def test_propagates_retrieve_result_when_allowed(self):
        config = MagicMock(auto_retrieval_enabled=True)
        service = RetrievalService()

        with patch.object(service, "retrieve", return_value=("block", True)):
            result = await service.retrieve_if_allowed("hello", session_id="s1", config=config)
            assert result == ("block", True)

    @pytest.mark.anyio
    async def test_explicit_recall_bypasses_turn_throttle(self):
        config = MagicMock(auto_retrieval_enabled=True)
        service = RetrievalService(record_recall_events=False)

        with patch.object(service, "retrieve", return_value=("block", False)) as retrieve:
            first = await service.retrieve_if_allowed(
                "te acordas del pipeline de memoria?",
                session_id="s1",
                config=config,
            )
            second = await service.retrieve_if_allowed(
                "te acordas del pipeline de memoria?",
                session_id="s1",
                config=config,
            )

        assert first == ("block", False)
        assert second == ("block", False)
        assert retrieve.call_count == 2
        assert retrieve.call_args_list[0].kwargs["source_filter"] is None
        assert retrieve.call_args_list[1].kwargs["source_filter"] is None
