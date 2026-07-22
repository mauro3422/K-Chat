from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.memory.synthesis.daily import generate_daily_synthesis


@pytest.mark.anyio
async def test_daily_synthesis_keeps_topic_clusters_with_activity(tmp_path):
    target = date(2026, 7, 11)
    cluster = {
        "label": "Memoria durable",
        "exchange_count": 3,
        "session_count": 1,
        "keyword_words": ["curador"],
    }

    with (
        patch("src.memory.synthesis.daily.resolve_memory_db_path", return_value=str(tmp_path / "memory.db")),
        patch(
            "src.memory.synthesis.daily.get_sessions_for_date",
            new=AsyncMock(return_value=[{"session_id": "s1", "name": "Prueba", "created_at": ""}]),
        ),
        patch(
            "src.memory.synthesis.daily.get_session_stats",
            new=AsyncMock(return_value={"message_count": 1, "first_message_time": "", "last_message_time": "", "duration": ""}),
        ),
        patch(
            "src.memory.synthesis.daily._get_message_activity_count",
            new=AsyncMock(return_value=1),
        ),
        patch("src.memory.synthesis.daily._get_session_topics", new=AsyncMock(return_value=[])),
        patch("src.memory.synthesis.daily._get_new_embeddings_count", new=AsyncMock(return_value=0)),
        patch("src.memory.synthesis.daily._get_new_memory_entries", new=AsyncMock(return_value=[])),
        patch("src.memory.synthesis.daily._get_new_entities", new=AsyncMock(return_value=[])),
        patch("src.memory.synthesis.daily._get_new_clusters", new=AsyncMock(return_value=[cluster])),
        patch("src.memory.synthesis.daily.load_session_summary_previews", return_value={}),
    ):
        report_path = await generate_daily_synthesis(
            db_path=str(tmp_path / "sessions.db"),
            target_date=target,
            root=tmp_path,
        )

    report = Path(report_path).read_text(encoding="utf-8")
    assert "## Topic Clusters" in report
    assert "Memoria durable" in report
