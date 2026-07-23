from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path
import time

import pytest

from src.coordination.lan_bridge import NodeLanBridge, parse_peer_urls
from src.coordination.lan_auth import LanRequestSigner
from src.coordination.memory_write_queue import MemoryWriteQueue
from src.coordination.node_state import NodeCoordinator


def test_parse_peer_urls_handles_commas_and_newlines() -> None:
    peers = parse_peer_urls("http://a:8000, https://b:9000/\nhttp://c:7000  ")
    assert peers == ["http://a:8000", "https://b:9000", "http://c:7000"]


def _config(peer_urls: str) -> SimpleNamespace:
    return SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        peer_urls=peer_urls,
        node_base_url="",
        node_id="node-a",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=12.0,
        sessions_db_path="",
        memory_db_path="",
    )


def _request_signer() -> LanRequestSigner:
    return LanRequestSigner("test-secret", "node-a")


def test_base_url_prefers_explicit_node_address_over_bind_host() -> None:
    cfg = SimpleNamespace(
        host="0.0.0.0",
        port=8000,
        peer_urls="",
        node_base_url="http://192.168.1.35:8000/",
        node_heartbeat_ttl=12.0,
    )
    bridge = NodeLanBridge(cfg, NodeCoordinator(cfg), lan_ip_resolver=lambda: "192.168.1.35")

    assert bridge.base_url == "http://192.168.1.35:8000"


def test_base_url_resolves_wildcard_bind_to_lan_address() -> None:
    cfg = SimpleNamespace(host="0.0.0.0", port=8000, peer_urls="", node_base_url="", node_heartbeat_ttl=12.0)

    bridge = NodeLanBridge(cfg, NodeCoordinator(cfg), lan_ip_resolver=lambda: "192.168.1.35")

    assert bridge.base_url == "http://192.168.1.35:8000"


def test_base_url_replaces_a_stale_configured_dhcp_address() -> None:
    cfg = SimpleNamespace(
        host="0.0.0.0",
        port=8000,
        peer_urls="",
        node_base_url="http://192.168.1.38:8000",
        node_heartbeat_ttl=12.0,
    )

    bridge = NodeLanBridge(cfg, NodeCoordinator(cfg), lan_ip_resolver=lambda: "192.168.1.39")

    assert bridge.base_url == "http://192.168.1.39:8000"


def test_discovered_peers_are_deduplicated_and_expire() -> None:
    cfg = SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        peer_urls="http://192.168.1.40:8000",
        node_base_url="",
        node_heartbeat_ttl=12.0,
        lan_discovery_ttl=20.0,
    )
    bridge = NodeLanBridge(cfg, NodeCoordinator(cfg), lan_ip_resolver=lambda: "192.168.1.35")

    now = time.monotonic()
    bridge.register_discovered_peer("http://192.168.1.40:8000/", seen_at=now)
    bridge.register_discovered_peer("http://192.168.1.41:8000", seen_at=now)

    bridge.prune_discovered_peers(now=now + 15.0)
    assert bridge.peer_urls == ["http://192.168.1.40:8000", "http://192.168.1.41:8000"]
    bridge.prune_discovered_peers(now=now + 21.0)
    assert bridge.peer_urls == ["http://192.168.1.40:8000"]


def test_discovered_peers_replace_a_stale_static_bootstrap_address() -> None:
    cfg = SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        peer_urls="http://192.168.1.38:8000",
        node_base_url="",
        node_heartbeat_ttl=12.0,
        lan_discovery_ttl=20.0,
        lan_discovery_enabled=True,
    )
    bridge = NodeLanBridge(cfg, NodeCoordinator(cfg), lan_ip_resolver=lambda: "192.168.1.35")

    bridge.register_discovered_peer("http://192.168.1.39:8000")

    assert bridge.peer_urls == ["http://192.168.1.39:8000"]


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"
        self.elapsed = SimpleNamespace(total_seconds=lambda: 0.012)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.calls.append((url, json))
        return self.responses[url]

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.calls.append((url, params or {}))
        return self.responses[url]


class _ConcurrentClient(_FakeClient):
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        super().__init__(responses)
        self.active_requests = 0
        self.max_active_requests = 0

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.active_requests += 1
        self.max_active_requests = max(self.max_active_requests, self.active_requests)
        try:
            await asyncio.sleep(0.01)
            return await super().get(url, params=params, headers=headers)
        finally:
            self.active_requests -= 1


class _FailThenSuccessClient:
    def __init__(self, responses: dict[str, _FakeResponse], failures: set[str]) -> None:
        self.responses = responses
        self.failures = failures
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.calls.append((url, json))
        if url in self.failures:
            raise RuntimeError("peer down")
        return self.responses[url]

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.calls.append((url, params or {}))
        if url in self.failures:
            raise RuntimeError("peer down")
        return self.responses[url]


class _FlakyResponse:
    def __init__(self, payload: dict, failures_before_success: int = 1) -> None:
        self._payload = payload
        self._remaining_failures = failures_before_success
        self.content = b"{}"
        self.elapsed = SimpleNamespace(total_seconds=lambda: 0.012)

    def raise_for_status(self) -> None:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise RuntimeError("HTTP 503")

    def json(self) -> dict:
        return self._payload


class _RetryClient:
    def __init__(self, response: _FlakyResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.calls.append((url, json))
        return self.response

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        self.calls.append((url, params or {}))
        return self.response


@pytest.mark.anyio
async def test_broadcast_once_posts_peer_heartbeat_and_records_remote_state() -> None:
    cfg = _config("http://peer-a:8000, http://peer-b:8000")
    coordinator = NodeCoordinator(cfg)

    responses = {
        "http://peer-a:8000/api/node/heartbeat": _FakeResponse(
            {"ok": True, "state": {"node_id": "peer-a", "role": "primary"}}
        ),
        "http://peer-b:8000/api/node/heartbeat": _FakeResponse(
            {"ok": True, "state": {"node_id": "peer-b", "role": "secondary"}}
        ),
    }
    fake_client = _FakeClient(responses)
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    result = await bridge.broadcast_once()

    assert result.sent == 2
    assert result.failed == 0
    assert fake_client.calls[0][0] == "http://peer-a:8000/api/node/heartbeat"
    assert fake_client.calls[1][0] == "http://peer-b:8000/api/node/heartbeat"

    snapshot = coordinator.snapshot()
    peer_ids = [peer["node_id"] for peer in snapshot["peers"]]
    assert peer_ids == ["peer-a", "peer-b"]


@pytest.mark.anyio
async def test_promoted_secondary_yields_when_preferred_primary_returns() -> None:
    cfg = SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        peer_urls="http://peer-a:8000",
        node_base_url="",
        node_id="secondary-node",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=12.0,
    )
    coordinator = NodeCoordinator(cfg)
    await coordinator.promote()
    response = _FakeResponse({
        "ok": True,
        "state": {"node_id": "primary-node", "role": "primary", "preferred_role": "primary"},
    })
    yielded: list[str] = []
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: _FakeClient({"http://peer-a:8000/api/node/heartbeat": response}),
        on_primary_yield=yielded.append,
        request_signer=_request_signer(),
    )

    await bridge.broadcast_once()

    assert await coordinator.is_primary() is False
    assert yielded == ["peer_primary_preferred"]


@pytest.mark.anyio
async def test_promoted_secondary_replays_queued_writes_when_preferred_primary_returns(tmp_path: Path) -> None:
    cfg = SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        peer_urls="http://peer-a:8000",
        node_base_url="",
        node_id="secondary-node",
        node_role="secondary",
        cluster_name="kairos",
        node_heartbeat_ttl=12.0,
    )
    coordinator = NodeCoordinator(cfg)
    await coordinator.promote()
    queue = MemoryWriteQueue(persistence_path=str(tmp_path / "queue.json"))
    queue.enqueue("Preferencia", "Python", source_node="secondary-node", reason="failover_replay_to_preferred_primary")
    response = _FakeResponse({
        "ok": True,
        "state": {"node_id": "primary-node", "role": "primary", "preferred_role": "primary"},
    })
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: _FakeClient({"http://peer-a:8000/api/node/heartbeat": response}),
        request_signer=_request_signer(),
    )
    mock_request = AsyncMock(return_value={"ok": True, "granted": True, "queued": False})

    with (
        patch("src.coordination.lan_bridge.get_memory_write_queue", return_value=queue),
        patch.object(NodeLanBridge, "request_memory_write", new=mock_request),
    ):
        await bridge.broadcast_once()

    assert await coordinator.is_primary() is False
    assert queue.snapshot() == []
    mock_request.assert_awaited_once()


@pytest.mark.anyio
async def test_broadcast_event_posts_to_each_peer() -> None:
    cfg = _config("http://peer-a:8000, http://peer-b:8000")
    coordinator = NodeCoordinator(cfg)

    responses = {
        "http://peer-a:8000/api/node/event": _FakeResponse({"ok": True}),
        "http://peer-b:8000/api/node/event": _FakeResponse({"ok": True}),
    }
    fake_client = _FakeClient(responses)
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    result = await bridge.broadcast_event("memory_updated", {"session_id": "s1"})

    assert result.sent == 2
    assert fake_client.calls[0][0] == "http://peer-a:8000/api/node/event"
    assert fake_client.calls[1][0] == "http://peer-b:8000/api/node/event"
    assert fake_client.calls[0][1]["type"] == "memory_updated"
    assert fake_client.calls[0][1]["data"] == {"session_id": "s1"}


@pytest.mark.anyio
async def test_request_memory_snapshot_gets_peer_diagnostics() -> None:
    cfg = _config("http://peer-a:8000")
    coordinator = NodeCoordinator(cfg)

    responses = {
        "http://peer-a:8000/api/memory/diagnostics": _FakeResponse(
            {
                "ok": True,
                "lease": None,
                "queue_size": 0,
                "queue": [],
                "queue_path": "/tmp/peer-queue.json",
                "memory": {"revision": 1.0, "sync": 2.0, "is_fresh": True},
                "compare": {"only_in_md": [], "only_in_db": [], "mismatched": [], "rename_candidates": []},
            }
        ),
    }
    fake_client = _FakeClient(responses)
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    result = await bridge.request_memory_snapshot(key_pattern="user:*")

    assert result["ok"] is True
    assert result["peer"] == "http://peer-a:8000"
    assert result["snapshot"]["queue_path"] == "/tmp/peer-queue.json"
    assert fake_client.calls[0][0] == "http://peer-a:8000/api/memory/diagnostics"
    assert fake_client.calls[0][1]["key_pattern"] == "user:*"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "path", "result_key"),
    [
        ("request_peer_memory_snapshots", "/api/memory/diagnostics", "snapshots"),
        ("request_peer_states", "/api/node/state", "states"),
    ],
)
async def test_peer_snapshot_requests_run_concurrently_and_preserve_peer_order(
    method_name: str,
    path: str,
    result_key: str,
) -> None:
    peers = "http://peer-a:8000, http://peer-b:8000"
    cfg = _config(peers)
    responses = {
        f"http://peer-a:8000{path}": _FakeResponse({"node_id": "peer-a"}),
        f"http://peer-b:8000{path}": _FakeResponse({"node_id": "peer-b"}),
    }
    client = _ConcurrentClient(responses)
    bridge = NodeLanBridge(
        cfg,
        NodeCoordinator(cfg),
        client_factory=lambda: client,
        request_signer=_request_signer(),
    )

    result = await getattr(bridge, method_name)()

    assert client.max_active_requests == 2
    assert [item["peer_url"] for item in result[result_key]] == [
        "http://peer-a:8000",
        "http://peer-b:8000",
    ]


@pytest.mark.anyio
async def test_peer_snapshot_requests_respect_configured_concurrency_limit() -> None:
    peers = "http://peer-a:8000, http://peer-b:8000, http://peer-c:8000"
    cfg = _config(peers)
    cfg.lan_snapshot_max_concurrency = 2
    responses = {
        f"http://peer-{peer}:8000/api/node/state": _FakeResponse({"node_id": f"peer-{peer}"})
        for peer in ("a", "b", "c")
    }
    client = _ConcurrentClient(responses)
    bridge = NodeLanBridge(
        cfg,
        NodeCoordinator(cfg),
        client_factory=lambda: client,
        request_signer=_request_signer(),
    )

    result = await bridge.request_peer_states()

    assert client.max_active_requests == 2
    assert [item["peer_url"] for item in result["states"]] == [
        "http://peer-a:8000",
        "http://peer-b:8000",
        "http://peer-c:8000",
    ]


@pytest.mark.anyio
async def test_request_session_directory_marks_peer_rows_as_remote() -> None:
    cfg = SimpleNamespace(
        host="127.0.0.1",
        port=8000,
        peer_urls="http://peer-a:8000",
        node_base_url="http://local:8000",
        node_heartbeat_ttl=12.0,
    )
    coordinator = NodeCoordinator(cfg)
    responses = {
        "http://peer-a:8000/api/node/sessions": _FakeResponse({
            "node": {"node_id": "peer-a", "role": "primary", "cluster_name": "kairos"},
            "sessions": [{
                "id": "remote-session",
                "name": "Remote",
                "source_mode": "local",
                "source_url": "http://0.0.0.0:8000",
            }],
        }),
    }
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: _FakeClient(responses),
        request_signer=_request_signer(),
    )

    result = await bridge.request_session_directory()

    assert result["sessions"][0]["source_mode"] == "peer"
    assert result["sessions"][0]["source_url"] == "http://peer-a:8000"


@pytest.mark.anyio
async def test_broadcast_event_retries_transient_failures() -> None:
    cfg = _config("http://peer-a:8000")
    coordinator = NodeCoordinator(cfg)
    flaky_response = _FlakyResponse({"ok": True}, failures_before_success=1)
    fake_client = _RetryClient(flaky_response)
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    with patch("src.coordination.lan_bridge.anyio.sleep", new=AsyncMock()):
        result = await bridge.broadcast_event("memory_updated", {"session_id": "s1"})

    assert result.sent == 1
    assert len(fake_client.calls) == 2


@pytest.mark.anyio
async def test_request_memory_write_falls_back_to_next_peer() -> None:
    cfg = _config("http://peer-a:8000, http://peer-b:8000")
    coordinator = NodeCoordinator(cfg)
    responses = {
        "http://peer-b:8000/api/node/memory/request": _FakeResponse({"ok": True, "granted": True, "queued": False}),
    }
    fake_client = _FailThenSuccessClient(
        responses,
        failures={"http://peer-a:8000/api/node/memory/request"},
    )
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    result = await bridge.request_memory_write("Preferencia", "Python")

    assert result["ok"] is True
    assert result["peer"] == "http://peer-b:8000"
    assert fake_client.calls[0][0] == "http://peer-a:8000/api/node/memory/request"
    assert fake_client.calls[-1][0] == "http://peer-b:8000/api/node/memory/request"
    assert len(fake_client.calls) >= 2


@pytest.mark.anyio
async def test_request_embedding_jobs_posts_to_primary_peer() -> None:
    cfg = _config("http://peer-a:8000")
    coordinator = NodeCoordinator(cfg)
    responses = {
        "http://peer-a:8000/api/node/embeddings/jobs": _FakeResponse(
            {"ok": True, "queued": False, "processed": [{"status": "dry_run"}]}
        ),
    }
    fake_client = _FakeClient(responses)
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    result = await bridge.request_embedding_jobs(
        [{"source": "session", "source_key": "s1", "item_idx": 0, "text": "hello"}],
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["peer"] == "http://peer-a:8000"
    assert fake_client.calls[0][0] == "http://peer-a:8000/api/node/embeddings/jobs"
    assert fake_client.calls[0][1]["dry_run"] is True
    assert fake_client.calls[0][1]["items"][0]["source_key"] == "s1"


@pytest.mark.anyio
async def test_broadcast_once_replays_pending_memory_writes_when_primary_returns(tmp_path: Path) -> None:
    cfg = _config("http://peer-a:8000")
    coordinator = NodeCoordinator(cfg)
    queue = MemoryWriteQueue(persistence_path=str(tmp_path / "queue.json"))
    queue.enqueue("Preferencia", "Python", source_node="node-a", reason="primary_unavailable")

    responses = {
        "http://peer-a:8000/api/node/heartbeat": _FakeResponse(
            {"ok": True, "state": {"node_id": "peer-a", "role": "primary", "base_url": "http://peer-a:8000"}}
        ),
    }
    fake_client = _FakeClient(responses)
    bridge = NodeLanBridge(
        cfg,
        coordinator,
        client_factory=lambda: fake_client,
        request_signer=_request_signer(),
    )

    mock_request = AsyncMock(return_value={"ok": True, "granted": True, "queued": False})

    with (
        patch("src.coordination.lan_bridge.get_memory_write_queue", return_value=queue),
        patch.object(NodeLanBridge, "request_memory_write", new=mock_request),
    ):
        result = await bridge.broadcast_once()

    assert result.sent == 1
    assert queue.snapshot() == []
    mock_request.assert_awaited_once()
