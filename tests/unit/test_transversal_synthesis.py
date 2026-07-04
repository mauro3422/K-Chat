import json
import sqlite3
from datetime import date

import pytest

from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.synthesis.morning_plan import build_morning_plan, render_morning_plan
from src.memory.synthesis.session import session_summary_path
from src.memory.synthesis.transversal import (
    candidates_from_transversal_synthesis_artifact,
    discover_transversal_synthesis_artifacts,
    generate_transversal_synthesis_candidates,
    generate_transversal_synthesis,
    transversal_synthesis_candidate_path,
    transversal_synthesis_path,
    vectorize_transversal_synthesis_artifacts,
)


class _TransversalStore:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE vec_meta (
                rowid INTEGER PRIMARY KEY,
                source TEXT,
                source_key TEXT,
                exchange_idx INTEGER,
                text TEXT,
                hash TEXT,
                content_hash TEXT,
                source_node_id TEXT DEFAULT ''
            )
            """
        )
        self.inserted: list[dict] = []

    def _get_conn(self):
        return self.conn

    def insert(self, _embedding, **kwargs) -> int:
        rowid = 20 + len(self.inserted)
        self.inserted.append(kwargs)
        self.conn.execute(
            """
            INSERT INTO vec_meta (
                rowid, source, source_key, exchange_idx, text, hash, content_hash, source_node_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs["exchange_idx"],
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
                kwargs.get("source_node_id", ""),
            ),
        )
        self.conn.commit()
        return rowid

    def close(self) -> None:
        self.conn.close()


def _write_summary(tmp_path, session_id: str, channel: str, body: str) -> None:
    path = session_summary_path(session_id, channel=channel, root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<!-- metadata: {'
        f'"session_id": "{session_id}", "channel": "{channel}", '
        '"created_at": "2026-07-02T08:00:00"'
        "} -->\n"
        f"# Session Summary - {session_id}\n\n{body}\n",
        encoding="utf-8",
    )


def test_generate_transversal_synthesis_detects_repeated_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    _write_summary(
        tmp_path,
        "s1",
        "web",
        "- Mauro quiere memoria por capas con embeddings y grafo.\n- Kairos necesita curadores nocturnos.",
    )
    _write_summary(
        tmp_path,
        "s2",
        "telegram",
        "- Mauro vuelve sobre memoria transversal y embeddings.\n- El curador debe conectar grafo y sesiones.",
    )

    first = generate_transversal_synthesis(root=tmp_path, target_date=date(2026, 7, 2))
    second = generate_transversal_synthesis(root=tmp_path, target_date=date(2026, 7, 2))

    path = transversal_synthesis_path(date(2026, 7, 2), root=tmp_path)
    text = path.read_text(encoding="utf-8")
    metadata = json.loads(text.split("<!-- metadata:", 1)[1].split("-->", 1)[0].strip())
    assert first["changed"] is True
    assert second["changed"] is False
    assert first["session_count"] == 2
    assert first["repeated_topic_count"] >= 1
    assert metadata["channels"] == {"telegram": 1, "web": 1}
    assert {source["channel"] for source in metadata["sources"]} == {"telegram", "web"}
    assert "Transversal Synthesis - 2026-07-02" in text
    assert path.parts[-5:-3] == ("memory", "transversal")
    assert "embedding" in text
    assert "Repeated Entities" in text


@pytest.mark.anyio
async def test_vectorize_transversal_synthesis_artifacts_embeds_and_marks_catalog(tmp_path, monkeypatch):
    path = transversal_synthesis_path(date(2026, 7, 2), root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<!-- metadata: {"date": "2026-07-02", "source": "transversal_synthesis"} -->\n'
        "# Transversal Synthesis - 2026-07-02\n\n- memoria embeddings grafo\n",
        encoding="utf-8",
    )
    store = _TransversalStore()
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    monkeypatch.setattr(
        "src.memory.embeddings.service.generate_embeddings_batch",
        lambda texts: [[0.2] * 384 for _ in texts],
    )

    try:
        result = await vectorize_transversal_synthesis_artifacts(
            root=tmp_path,
            store=store,
            catalog=catalog,
            source_node_id="pc",
        )
    finally:
        store.close()

    row = catalog.get(source="transversal_synthesis", source_key="2026-07-02", item_idx=-1)
    assert result == {"artifacts": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}
    assert row is not None
    assert row["status"] == "embedded"
    assert row["pipeline"] == "transversal_synthesis_embedding"
    assert row["source_node_id"] == "pc"


def test_morning_plan_includes_transversal_synthesis(tmp_path):
    path = transversal_synthesis_path(date(2026, 7, 2), root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<!-- metadata: {"channels": {"telegram": 1, "web": 1}, "date": "2026-07-02", "source": "transversal_synthesis"} -->\n'
        "# Transversal Synthesis - 2026-07-02\n\n## Repeated Topics\n\n- `memoria`: 2 mentions\n",
        encoding="utf-8",
    )

    plan = build_morning_plan(root=tmp_path, target_date=date(2026, 7, 2))
    rendered = render_morning_plan(plan)

    assert plan["transversal_synthesis"]["path"] == str(path)
    assert plan["transversal_synthesis"]["metadata"]["channels"] == {"telegram": 1, "web": 1}
    assert "Latest transversal synthesis" in rendered
    assert "Channels covered: telegram: 1, web: 1" in rendered
    assert "Transversal Signals" in rendered


def test_discover_transversal_synthesis_artifacts_reads_metadata(tmp_path):
    path = transversal_synthesis_path(date(2026, 7, 2), root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<!-- metadata: {"date": "2026-07-02", "source": "transversal_synthesis"} -->\n'
        "# Transversal Synthesis - 2026-07-02\n",
        encoding="utf-8",
    )

    artifacts = discover_transversal_synthesis_artifacts(root=tmp_path)

    assert artifacts[0]["date"] == "2026-07-02"
    assert artifacts[0]["metadata"]["source"] == "transversal_synthesis"
    assert artifacts[0]["content_hash"]


def test_candidates_from_transversal_synthesis_artifact_extracts_review_items(tmp_path):
    path = transversal_synthesis_path(date(2026, 7, 2), root=tmp_path)
    text = (
        '<!-- metadata: {"date": "2026-07-02", "source": "transversal_synthesis"} -->\n'
        "# Transversal Synthesis - 2026-07-02\n\n"
        "## Repeated Topics\n\n"
        "- `memoria`: 3 mentions across 2 sessions (s1, s2)\n"
        "  - web:s1 Mauro quiere memoria por capas con embeddings.\n"
        "  - telegram:s2 Hay que conectar memoria con grafo.\n\n"
        "## Repeated Entities\n\n"
        "- Mauro: 2 mentions across 2 sessions (s1, s2)\n"
    )
    artifact = {
        "date": "2026-07-02",
        "path": str(path),
        "text": text,
        "content_hash": "hash-1",
        "metadata": {
            "channels": {"telegram": 1, "web": 1},
            "date": "2026-07-02",
            "source": "transversal_synthesis",
            "sources": [
                {"session_id": "s1", "channel": "web", "path": "memory/session_summaries/web/s1.md"},
                {"session_id": "s2", "channel": "telegram", "path": "memory/session_summaries/telegram/s2.md"},
            ],
        },
    }

    candidates = candidates_from_transversal_synthesis_artifact(artifact, timestamp="2026-07-02T10:00:00")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["type"] == "transversal_synthesis_candidate"
    assert candidate["source"] == "transversal_synthesis"
    assert candidate["relation_type"] == "LINKS_TO"
    assert candidate["target_id"] == "memory:semantic-neighbor"
    assert candidate["target_needs_resolution"] is True
    assert candidate["source_channels"] == {"telegram": 1, "web": 1}
    assert {item["session_id"] for item in candidate["source_sessions"]} == {"s1", "s2"}
    assert candidate["provenance"]["channels"] == {"telegram": 1, "web": 1}
    assert candidate["source_id"].startswith("candidate:")
    assert candidate["temporal"]["status"] == "reinforced"
    assert {entity["name"] for entity in candidate["entities"]} >= {"Mauro", "memoria"}
    assert any(relation["target_id"] == "session:s1" for relation in candidate["proposed_relations"])
    assert any(relation["target_id"] == "session:s2" for relation in candidate["proposed_relations"])
    assert any(relation["relation_type"] == "DERIVED_FROM" for relation in candidate["proposed_relations"])
    assert any(relation["needs_resolution"] for relation in candidate["proposed_relations"] if relation["relation_type"] == "LINKS_TO")


def test_generate_transversal_synthesis_candidates_writes_idempotent_jsonl(tmp_path):
    path = transversal_synthesis_path(date(2026, 7, 2), root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<!-- metadata: {"date": "2026-07-02", "source": "transversal_synthesis"} -->\n'
        "# Transversal Synthesis - 2026-07-02\n\n"
        "## Repeated Topics\n\n"
        "- `memoria`: 3 mentions across 2 sessions (s1, s2)\n"
        "  - web:s1 Mauro quiere memoria por capas con embeddings.\n"
        "  - telegram:s2 Hay que conectar memoria con grafo.\n",
        encoding="utf-8",
    )

    first = generate_transversal_synthesis_candidates(
        root=tmp_path,
        target_date=date(2026, 7, 2),
        timestamp="2026-07-02T10:00:00",
    )
    second = generate_transversal_synthesis_candidates(
        root=tmp_path,
        target_date=date(2026, 7, 2),
        timestamp="2026-07-02T10:00:00",
    )
    candidate_path = transversal_synthesis_candidate_path(date(2026, 7, 2), root=tmp_path)

    rows = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines()]
    assert first["created"] == 1
    assert first["total"] == 1
    assert second["created"] == 0
    assert rows[0]["source_artifact"] == str(path)
    assert rows[0]["source"] == "transversal_synthesis"
