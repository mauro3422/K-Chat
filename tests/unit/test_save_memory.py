from unittest.mock import AsyncMock
import json
import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch
from types import SimpleNamespace


from src.coordination.memory_write_queue import get_memory_write_queue
from src.coordination.node_state import NodeCoordinator, configure_node_coordinator, reset_node_coordinator
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.tools.save_memory import _save_memory_inbox, run as save_memory_run

@pytest.fixture
def temp_memory_file():
    # Crear un archivo temporal para MEMORY.md y mockear CONTEXT_DIR para apuntar al directorio temporal
    temp_dir = tempfile.mkdtemp()
    temp_filepath = os.path.join(temp_dir, "MEMORY.md")
    
    # Escribir contenido inicial
    with open(temp_filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test-user\n\n")
        
    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        yield temp_filepath
        
    # Limpieza
    try:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        os.rmdir(temp_dir)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_node_coord():
    reset_node_coordinator()
    yield
    reset_node_coordinator()

@pytest.mark.anyio
async def test_save_memory_create_new_key(temp_memory_file):
    res = await save_memory_run(key="Preferencia", value="Python", scope="canonical")
    assert "saved" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "User: " in content
    assert "System: test-user" in content
    assert "## Memories" in content
    assert "- **Preferencia**: Python" in content

@pytest.mark.anyio
async def test_save_memory_update_key(temp_memory_file):
    await save_memory_run(key="Preferencia", value="Python", scope="canonical")
    res = await save_memory_run(key="Preferencia", value="TypeScript", scope="canonical")
    assert "saved" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "- **Preferencia**: TypeScript" in content
    assert "- **Preferencia**: Python" not in content

@pytest.mark.anyio
async def test_save_memory_delete_key(temp_memory_file):
    await save_memory_run(key="Preferencia", value="Python", scope="canonical")
    res = await save_memory_run(key="Preferencia", value="")
    assert "deleted" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "Preferencia" not in content

@pytest.mark.anyio
async def test_save_memory_empty_key(temp_memory_file):
    res = await save_memory_run(key="", value="Algo", scope="canonical")
    assert "ERROR" in res

@pytest.mark.anyio
async def test_save_memory_delete_nonexistent_key(temp_memory_file):
    res = await save_memory_run(key="Inexistente", value="")
    assert "did not exist" in res


@pytest.mark.anyio
async def test_save_memory_defaults_to_inbox_without_touching_memory_md(temp_memory_file, tmp_path):
    before = open(temp_memory_file, "r", encoding="utf-8").read()

    res = await save_memory_run(
        key="user:workflow",
        value="2026-07-02 10:00 | Mauro wants save_memory as a curator inbox.",
        _root=tmp_path,
        _session_id="sess-1",
        channel="web",
        message_ref="turn-7",
        urgency="high",
    )

    after = open(temp_memory_file, "r", encoding="utf-8").read()
    inbox_files = list((tmp_path / "memory").rglob("**/inbox.jsonl"))
    payload = json.loads(inbox_files[0].read_text(encoding="utf-8").splitlines()[0])

    assert "[OK] queued memory inbox item" in res
    assert before == after
    assert payload["key"] == "user:workflow"
    assert payload["status"] == "pending"
    assert payload["session_id"] == "sess-1"
    assert payload["channel"] == "web"
    assert payload["message_ref"] == "turn-7"
    assert payload["urgency"] == "high"


@pytest.mark.anyio
async def test_save_memory_inbox_embeddings_use_inbox_source(temp_memory_file, tmp_path):
    store = _VectorStoreFake()
    repos = SimpleNamespace(memory=SimpleNamespace(vector_store=store))

    with (
        patch("src.memory.embeddings.service.generate_embedding", return_value=[0.1, 0.2]),
        patch("src.memory.keywords.extractor.extract_keywords", return_value=[("memoria", 1.0)]),
    ):
        result = await save_memory_run(
            key="user:workflow",
            value="2026-07-02 10:00 | Inbox items should be embedded separately.",
            _repos=repos,
            _root=tmp_path,
        )

    row = store.conn.execute("SELECT source, source_key, text FROM vec_meta").fetchone()

    assert "[OK] queued memory inbox item" in result
    assert row[0] == "memory_inbox"
    assert row[1]
    assert "Inbox items" in row[2]
    store.conn.close()


@pytest.mark.anyio
async def test_save_memory_blocked_on_secondary_node(temp_memory_file):
    coordinator = NodeCoordinator(type("Cfg", (), {"peer_urls": "http://peer-a:8000"})())
    await coordinator.demote()
    configure_node_coordinator(coordinator)

    with (
        patch("src.tools.save_memory.NodeLanBridge.request_memory_write", new=AsyncMock(return_value={"ok": False, "queued": True, "error": "down"})),
        patch("src.tools.save_memory.NodeLanBridge.broadcast_event", new=AsyncMock(return_value={"ok": True})) as mock_broadcast,
    ):
        res = await save_memory_run(key="Preferencia", value="Python", scope="canonical")

    assert "queued" in res
    queue = get_memory_write_queue()
    pending = queue.snapshot()
    assert pending and pending[0]["key"] == "Preferencia"
    broadcasted = [call.args[0] for call in mock_broadcast.call_args_list]
    assert broadcasted == ["memory_write_queued"]

    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "- **Preferencia**: Python" not in content


@pytest.mark.anyio
async def test_save_memory_injects_lan_signer_into_secondary_bridge(temp_memory_file):
    coordinator = NodeCoordinator(
        type("Cfg", (), {"peer_urls": "http://peer-a:8000"})()
    )
    await coordinator.demote()
    configure_node_coordinator(coordinator)
    signer = object()

    with patch("src.tools.save_memory.NodeLanBridge") as bridge_type:
        bridge = bridge_type.return_value
        bridge.request_memory_write = AsyncMock(
            return_value={"ok": False, "queued": True, "error": "down"}
        )
        bridge.broadcast_event = AsyncMock(return_value={"ok": True})
        result = await save_memory_run(
            key="Preferencia",
            value="Python",
            scope="canonical",
            _lan_request_signer=signer,
        )

    assert "queued" in result
    assert bridge_type.call_count == 2
    assert all(
        call.kwargs["request_signer"] is signer
        for call in bridge_type.call_args_list
    )


@pytest.mark.anyio
async def test_save_memory_broadcasts_memory_updated_event(temp_memory_file):
    coordinator = NodeCoordinator(type("Cfg", (), {"peer_urls": "http://peer-a:8000", "node_heartbeat_ttl": 30.0})())
    await coordinator.promote()
    configure_node_coordinator(coordinator)

    fake_lease_manager = type("LeaseMgr", (), {"acquire": lambda self, *a, **k: object()})()
    with (
        patch("src.tools.save_memory.get_memory_lease_manager", return_value=fake_lease_manager),
        patch("src.tools.save_memory.NodeLanBridge.broadcast_event", new=AsyncMock(return_value={"ok": True})) as mock_broadcast,
    ):
        res = await save_memory_run(key="Preferencia", value="Python", scope="canonical")

    assert "[OK]" in res
    assert coordinator.snapshot()["last_memory_revision"] > 0
    assert coordinator.snapshot()["last_memory_sync"] > 0
    broadcasted = [call.args[0] for call in mock_broadcast.call_args_list]
    assert broadcasted == ["memory_updated", "memory_synced", "memory_write_completed"]
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "- **Preferencia**: Python" in content


class _MemoryIndexFake:
    async def upsert(self, key, value):
        return None

    async def get(self, key):
        return None

    async def delete(self, key):
        return None


class _VectorStoreFake:
    def __init__(self):
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
                created_at TEXT
            )
            """
        )
        self.conn.execute("CREATE TABLE vec_keywords (rowid INTEGER, word TEXT, score REAL)")
        self.conn.commit()

    def _get_conn(self):
        return self.conn

    def delete_by_source(self, source_key, source=""):
        self.conn.execute("DELETE FROM vec_meta WHERE source=? AND source_key=?", (source, source_key))
        self.conn.commit()
        return 0

    def insert(self, embedding, **kwargs):
        rowid = 10
        self.conn.execute(
            """
            INSERT INTO vec_meta (rowid, source, source_key, exchange_idx, text, hash, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                rowid,
                kwargs["source"],
                kwargs["source_key"],
                kwargs.get("exchange_idx", 0),
                kwargs["text"],
                kwargs["hash"],
                kwargs["content_hash"],
            ),
        )
        self.conn.commit()
        return rowid


@pytest.mark.anyio
async def test_save_memory_registers_memory_embedding_in_work_catalog(temp_memory_file, tmp_path):
    catalog = MemoryWorkCatalogRepository(str(tmp_path / "memory.db"))
    store = _VectorStoreFake()
    repos = SimpleNamespace(
        memory=SimpleNamespace(
            memory_index=_MemoryIndexFake(),
            vector_store=store,
            work_catalog=catalog,
        )
    )

    with (
        patch("src.memory.embeddings.service.generate_embedding", return_value=[0.1, 0.2]),
        patch("src.memory.keywords.extractor.extract_keywords", return_value=[("python", 1.0)]),
    ):
        result = await save_memory_run(
            key="user:preference",
            value="2026-07-01 10:00 | Mauro prefers cataloged memory writes.",
            scope="canonical",
            _repos=repos,
        )

    row = catalog.get(
        source="memory",
        source_key="user:preference",
        item_idx=0,
        pipeline="memory_entry_embedding",
        pipeline_version="1",
        model_id="fastembed-default",
        model_version="default",
    )
    assert "[OK]" in result
    assert row is not None
    assert row["status"] == "embedded"
    assert row["vec_rowid"] == 10
    store.conn.close()


@pytest.mark.anyio
async def test_save_memory_inbox_retry_is_idempotent_with_provenance(tmp_path):
    first = await _save_memory_inbox(
        "decision:review-policy",
        "Mauro wants human review before promotion.",
        root=str(tmp_path),
        session_id="session-1",
        channel="web",
        message_ref="message-1",
    )
    second = await _save_memory_inbox(
        "decision:review-policy",
        "Mauro wants human review before promotion.",
        root=str(tmp_path),
        session_id="session-1",
        channel="web",
        message_ref="message-1",
    )

    assert "queued memory inbox item" in first
    assert "already pending" in second


@pytest.mark.anyio
async def test_save_memory_inbox_without_provenance_keeps_observations_separate(tmp_path):
    first = await _save_memory_inbox(
        "decision:review-policy",
        "Mauro wants human review before promotion.",
        root=str(tmp_path),
        channel="web",
    )
    second = await _save_memory_inbox(
        "decision:review-policy",
        "Mauro wants human review before promotion.",
        root=str(tmp_path),
        channel="web",
    )

    assert "queued memory inbox item" in first
    assert "queued memory inbox item" in second
