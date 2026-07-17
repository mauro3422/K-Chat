from types import SimpleNamespace

import httpx
import pytest

from scripts.lan_auth_client import build_json_request
from src.coordination.lan_auth import (
    LanRequestSigner,
    LanRequestVerifier,
    encode_json_body,
)
from src.coordination.lan_bridge import NodeLanBridge
from src.coordination.node_state import NodeCoordinator


def _signer(now: float = 1_000.0) -> LanRequestSigner:
    return LanRequestSigner(
        "shared-test-secret",
        "node-a",
        clock=lambda: now,
        nonce_factory=lambda: "a" * 32,
    )


def _verifier(now: float = 1_000.0) -> LanRequestVerifier:
    return LanRequestVerifier(
        "shared-test-secret",
        {"node-a"},
        clock=lambda: now,
    )


def test_valid_signature_is_accepted():
    body = encode_json_body({"key": "user:test", "value": "ok"})
    assert body == httpx.Request(
        "POST",
        "http://peer/api/node/memory/request",
        json={"key": "user:test", "value": "ok"},
    ).content
    headers = _signer().sign_headers("POST", "/api/node/memory/request", body)

    result = _verifier().verify(
        "POST",
        "/api/node/memory/request",
        body,
        headers,
    )

    assert result.ok is True
    assert result.node_id == "node-a"


def test_missing_configuration_and_credentials_fail_closed():
    unconfigured = LanRequestVerifier("", {"node-a"})
    assert unconfigured.verify("POST", "/api/node/promote", b"", {}).code == "configuration_missing"

    configured = _verifier()
    assert configured.verify("POST", "/api/node/promote", b"", {}).code == "missing_credentials"


def test_unlisted_node_identity_is_rejected():
    headers = LanRequestSigner(
        "shared-test-secret",
        "node-c",
        clock=lambda: 1_000.0,
        nonce_factory=lambda: "c" * 32,
    ).sign_headers("POST", "/api/node/promote")

    result = _verifier().verify(
        "POST",
        "/api/node/promote",
        b"",
        headers,
    )

    assert result.code == "node_not_allowed"


def test_invalid_signature_and_altered_body_are_rejected():
    body = encode_json_body({"value": "original"})
    headers = _signer().sign_headers("POST", "/api/node/event", body)

    invalid_headers = dict(headers)
    invalid_headers["X-Kairos-Signature"] = "0" * 64
    assert _verifier().verify("POST", "/api/node/event", body, invalid_headers).code == "invalid_signature"

    altered = encode_json_body({"value": "altered"})
    assert _verifier().verify("POST", "/api/node/event", altered, headers).code == "invalid_signature"


@pytest.mark.parametrize(
    ("timestamp", "expected_code"),
    (
        (969, "timestamp_expired"),
        (1_031, "timestamp_in_future"),
    ),
)
def test_timestamp_outside_window_is_rejected(timestamp, expected_code):
    headers = _signer().sign_headers(
        "POST",
        "/api/node/promote",
        timestamp=timestamp,
    )

    result = _verifier().verify(
        "POST",
        "/api/node/promote",
        b"",
        headers,
    )

    assert result.code == expected_code


def test_nonce_replay_is_rejected_and_cleanup_releases_state():
    verifier = _verifier()
    headers = _signer().sign_headers("POST", "/api/node/promote")

    assert verifier.verify("POST", "/api/node/promote", b"", headers).ok is True
    assert verifier.verify("POST", "/api/node/promote", b"", headers).code == "nonce_replayed"
    assert verifier.tracked_nonce_count == 1

    verifier.clear()
    assert verifier.tracked_nonce_count == 0


def test_standard_library_client_signs_sensitive_request(monkeypatch):
    monkeypatch.setenv("KAIROS_LAN_SHARED_SECRET", "shared-test-secret")
    request = build_json_request(
        "POST",
        "http://peer:8000/api/node/memory/request",
        payload={"key": "user:test", "value": "ok"},
        signer=_signer(),
    )

    result = _verifier().verify(
        "POST",
        "/api/node/memory/request",
        request.data or b"",
        dict(request.header_items()),
    )

    assert result.ok is True


class _Response:
    content = b"{}"
    elapsed = SimpleNamespace(total_seconds=lambda: 0.01)

    def json(self):
        return {"ok": True, "state": {"node_id": "node-b", "role": "secondary"}}

    def raise_for_status(self):
        return None


class _CapturingClient:
    def __init__(self):
        self.json = None
        self.headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, _url, *, json, headers):
        self.json = json
        self.headers = headers
        return _Response()


@pytest.mark.anyio
async def test_node_lan_bridge_signs_internal_requests():
    config = SimpleNamespace(
        node_id="node-a",
        node_role="primary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
        node_base_url="http://node-a:8000",
        peer_urls="http://node-b:8000",
        host="127.0.0.1",
        port=8000,
    )
    coordinator = NodeCoordinator(config)
    client = _CapturingClient()
    signer = _signer()
    bridge = NodeLanBridge(
        config,
        coordinator,
        client_factory=lambda: client,
        request_signer=signer,
    )

    result = await bridge.broadcast_once()

    verification = _verifier().verify(
        "POST",
        "/api/node/heartbeat",
        encode_json_body(client.json),
        client.headers,
    )
    assert result.sent == 1
    assert verification.ok is True
