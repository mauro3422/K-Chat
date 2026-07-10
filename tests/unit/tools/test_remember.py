import pytest

from src.memory.retrieval.hybrid_retriever import HybridResult
from src.tools.remember import DEFINITION, run


class FakeHybridRetriever:
    async def search(self, query, top_k=5, source_filter=None):
        return [
            HybridResult(
                rowid=1,
                text="Mauro quiere memoria canonica con grafo.",
                source="memory",
                source_key="user:memory-policy",
                fusion_score=0.9,
                rank=1,
            ),
            HybridResult(
                rowid=2,
                text="Candidato sobre embeddings y relaciones.",
                source="memory_candidate",
                source_key="cand-1",
                fusion_score=0.74,
                rank=2,
            ),
        ]


class FakeMemoryRepos:
    def __init__(self):
        self.hybrid_retriever = FakeHybridRetriever()


class FakeRepos:
    def __init__(self):
        self.memory = FakeMemoryRepos()


class TestRememberDefinition:
    def test_definition_structure(self):
        assert DEFINITION["type"] == "function"
        fdef = DEFINITION["function"]
        assert fdef["name"] == "remember"
        props = fdef["parameters"]["properties"]
        assert "query" in fdef["parameters"]["required"]
        assert props["intent"]["default"] == "recall"
        assert "link" in props["intent"]["enum"]
        assert "memory_candidate" in props["source"]["enum"]
        assert "memory_inbox" in props["source"]["enum"]


class TestRememberRun:
    @pytest.mark.anyio
    async def test_empty_query_returns_error(self):
        result = await run(query="  ")

        assert "[ERROR]" in result
        assert "empty" in result.lower()

    @pytest.mark.anyio
    async def test_auto_weak_signal_skips_recall(self):
        result = await run(query="hola como va", intent="auto", record_event=False)

        assert "No active recall triggered" in result
        assert "weak_signal" in result

    @pytest.mark.anyio
    async def test_recall_intent_calls_recall_memories(self, monkeypatch):
        async def fake_recall(**kwargs):
            assert kwargs["query"] == "Te acordas del pipeline de memoria?"
            assert kwargs["include_graph_context"] is True
            return "recuerdo encontrado"

        monkeypatch.setattr("src.tools.recall_memories.run", fake_recall)

        result = await run(
            query="Te acordas del pipeline de memoria?",
            record_event=False,
        )

        assert "recuerdo encontrado" in result
        assert "explicit_recall" in result

    @pytest.mark.anyio
    async def test_recall_intent_adds_semantic_relation_hints(self, monkeypatch):
        async def fake_recall(**kwargs):
            return "recuerdo encontrado"

        monkeypatch.setattr("src.tools.recall_memories.run", fake_recall)

        result = await run(
            query="Te acordas de la memoria con grafo?",
            _repos=FakeRepos(),
            record_event=False,
        )

        assert "## Semantic relation hints" in result
        assert "candidate:cand-1" in result
        assert "REFINES" in result
        assert "curator_workbench action=upsert_relation" in result

    @pytest.mark.anyio
    async def test_link_intent_adds_link_hint(self, monkeypatch):
        async def fake_recall(**kwargs):
            return "memoria relacionada"

        monkeypatch.setattr("src.tools.recall_memories.run", fake_recall)

        result = await run(
            query="Kairos memoria pipeline",
            intent="link",
            known_entities=["Kairos"],
            semantic_score=0.9,
            entity_overlap=0.6,
            keyword_overlap=0.4,
            record_event=False,
        )

        assert "memoria relacionada" in result
        assert "## Link hint" in result
        assert "links_to" in result

    @pytest.mark.anyio
    async def test_verify_intent_adds_verification_policy(self, monkeypatch):
        async def fake_recall(**kwargs):
            return "memoria previa"

        monkeypatch.setattr("src.tools.recall_memories.run", fake_recall)

        result = await run(
            query="Esto contradice lo anterior?",
            intent="verify",
            contradiction_score=0.8,
            record_event=False,
        )

        assert "## Verification policy" in result
        assert "CONTRADICTS" in result

    @pytest.mark.anyio
    async def test_record_event_writes_recall_artifact(self, monkeypatch, tmp_path):
        async def fake_recall(**kwargs):
            return "memoria previa"

        monkeypatch.setattr("src.tools.recall_memories.run", fake_recall)

        result = await run(
            query="Te acordas de Kairos?",
            record_event=True,
            _root=tmp_path,
        )

        artifact = tmp_path / "memory"
        assert "## Recall event" in result
        assert list(artifact.glob("*/*/*/recall.jsonl"))
