from pathlib import Path


def test_memory_lease_manager_blocks_other_owner(tmp_path):
    from src.coordination.memory_lease import MemoryLeaseManager

    lease_path = tmp_path / "memory.lease.json"
    manager = MemoryLeaseManager(lease_path=str(lease_path))

    first = manager.acquire("node-a", ttl=30.0)
    assert first is not None
    assert first.owner_node_id == "node-a"

    blocked = manager.acquire("node-b", ttl=30.0)
    assert blocked is None
    assert manager.is_active("node-a") is True
    assert Path(lease_path).exists()


def test_memory_lease_manager_allows_reacquire_after_expiry(tmp_path):
    from src.coordination.memory_lease import MemoryLeaseManager

    lease_path = tmp_path / "memory.lease.json"
    manager = MemoryLeaseManager(lease_path=str(lease_path))

    lease = manager.acquire("node-a", ttl=0.01)
    assert lease is not None

    import time

    time.sleep(0.02)
    reacquired = manager.acquire("node-b", ttl=30.0)
    assert reacquired is not None
    assert reacquired.owner_node_id == "node-b"

