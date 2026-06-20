from unittest.mock import AsyncMock
import os
import tempfile
import pytest
from unittest.mock import patch


from src.coordination.memory_write_queue import get_memory_write_queue
from src.coordination.node_state import NodeCoordinator, configure_node_coordinator, reset_node_coordinator
from src.tools.save_memory import run as save_memory_run

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
    res = await save_memory_run(key="Preferencia", value="Python")
    assert "saved" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "User: " in content
    assert "System: test-user" in content
    assert "## Memories" in content
    assert "- **Preferencia**: Python" in content

@pytest.mark.anyio
async def test_save_memory_update_key(temp_memory_file):
    await save_memory_run(key="Preferencia", value="Python")
    res = await save_memory_run(key="Preferencia", value="TypeScript")
    assert "saved" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "- **Preferencia**: TypeScript" in content
    assert "- **Preferencia**: Python" not in content

@pytest.mark.anyio
async def test_save_memory_delete_key(temp_memory_file):
    await save_memory_run(key="Preferencia", value="Python")
    res = await save_memory_run(key="Preferencia", value="")
    assert "deleted" in res
    
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "Preferencia" not in content

@pytest.mark.anyio
async def test_save_memory_empty_key(temp_memory_file):
    res = await save_memory_run(key="", value="Algo")
    assert "ERROR" in res

@pytest.mark.anyio
async def test_save_memory_delete_nonexistent_key(temp_memory_file):
    res = await save_memory_run(key="Inexistente", value="")
    assert "did not exist" in res


@pytest.mark.anyio
async def test_save_memory_blocked_on_secondary_node(temp_memory_file):
    coordinator = NodeCoordinator(type("Cfg", (), {"peer_urls": "http://peer-a:8000"})())
    await coordinator.demote()
    configure_node_coordinator(coordinator)

    with (
        patch("src.tools.save_memory.NodeLanBridge.request_memory_write", new=AsyncMock(return_value={"ok": False, "queued": True, "error": "down"})),
        patch("src.tools.save_memory.NodeLanBridge.broadcast_event", new=AsyncMock(return_value={"ok": True})) as mock_broadcast,
    ):
        res = await save_memory_run(key="Preferencia", value="Python")

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
async def test_save_memory_broadcasts_memory_updated_event(temp_memory_file):
    coordinator = NodeCoordinator(type("Cfg", (), {"peer_urls": "http://peer-a:8000", "node_heartbeat_ttl": 30.0})())
    await coordinator.promote()
    configure_node_coordinator(coordinator)

    fake_lease_manager = type("LeaseMgr", (), {"acquire": lambda self, *a, **k: object()})()
    with (
        patch("src.tools.save_memory.get_memory_lease_manager", return_value=fake_lease_manager),
        patch("src.tools.save_memory.NodeLanBridge.broadcast_event", new=AsyncMock(return_value={"ok": True})) as mock_broadcast,
    ):
        res = await save_memory_run(key="Preferencia", value="Python")

    assert "[OK]" in res
    assert coordinator.snapshot()["last_memory_revision"] > 0
    assert coordinator.snapshot()["last_memory_sync"] > 0
    broadcasted = [call.args[0] for call in mock_broadcast.call_args_list]
    assert broadcasted == ["memory_updated", "memory_synced", "memory_write_completed"]
    with open(temp_memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "- **Preferencia**: Python" in content
