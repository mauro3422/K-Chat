from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.coordination.lan_auth import (
    LanRequestSigner,
    LanRequestVerifier,
    encode_json_body,
)
from src.coordination.node_state import NodeCoordinator
from web.routers.node import router as node_router
from web.routers.node_memory import router as node_memory_router
from web.routers.memory import router as memory_router
from web.services.lan_auth import LanAuthGuard


class _Bridge:
    peer_urls: list[str] = []

    def register_discovered_peer(self, peer_url: str) -> None:
        self.peer_urls.append(peer_url)


def _app(
    *,
    secret: str = "shared-test-secret",
    testing: bool = False,
    allow_loopback: bool = False,
    max_body_bytes: int = 3 * 1024 * 1024,
) -> FastAPI:
    config = SimpleNamespace(
        node_id="node-a",
        node_role="primary",
        cluster_name="kairos",
        node_heartbeat_ttl=10.0,
    )
    app = FastAPI()
    app.state.config = config
    app.state.node_coordinator = NodeCoordinator(config)
    app.state.node_bridge = _Bridge()
    app.state.lan_auth_guard = LanAuthGuard(
        LanRequestVerifier(secret, {"node-a", "node-b"}),
        testing=testing,
        allow_unsigned_loopback=allow_loopback,
        max_body_bytes=max_body_bytes,
    )
    app.include_router(node_router)
    app.include_router(node_memory_router)
    app.include_router(memory_router)
    return app


def _signed_headers(payload: dict, *, signature_secret: str = "shared-test-secret"):
    body = encode_json_body(payload)
    signer = LanRequestSigner(
        signature_secret,
        "node-b",
        nonce_factory=lambda: "b" * 32,
    )
    headers = signer.sign_headers("POST", "/api/node/heartbeat", body)
    headers["Content-Type"] = "application/json"
    return body, headers


def test_valid_signature_reaches_sensitive_endpoint():
    app = _app()
    payload = {
        "node_id": "node-b",
        "role": "secondary",
        "base_url": "http://192.168.1.22:8000",
    }
    body, headers = _signed_headers(payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/node/heartbeat",
            content=body,
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["state"]["peers"][0]["node_id"] == "node-b"


def test_missing_and_invalid_signatures_are_rejected():
    app = _app()
    payload = {"node_id": "node-b", "role": "secondary"}
    body, invalid_headers = _signed_headers(
        payload,
        signature_secret="wrong-secret",
    )

    with TestClient(app) as client:
        missing = client.post("/api/node/heartbeat", json=payload)
        invalid = client.post(
            "/api/node/heartbeat",
            content=body,
            headers=invalid_headers,
        )

    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "missing_credentials"
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "invalid_signature"


def test_signed_identity_must_match_claimed_node_id():
    app = _app()
    payload = {"node_id": "node-a", "role": "secondary"}
    body, headers = _signed_headers(payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/node/heartbeat",
            content=body,
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "lan_node_identity_mismatch"


def test_missing_server_secret_locks_sensitive_routes_but_not_public_state():
    app = _app(secret="")

    with TestClient(app) as client:
        sensitive = client.post(
            "/api/node/heartbeat",
            json={"node_id": "node-b", "role": "secondary"},
        )
        public = client.get("/api/node/state")

    assert sensitive.status_code == 503
    assert sensitive.json()["detail"]["code"] == "configuration_missing"
    assert public.status_code == 200
    assert public.json()["node_id"] == "node-a"


def test_memory_and_administrative_endpoints_are_protected():
    app = _app()

    with TestClient(app) as client:
        responses = [
            client.get("/api/node/sessions"),
            client.get("/api/node/memory/queue"),
            client.get("/api/node/sync/status"),
            client.get("/api/memory/diagnostics"),
            client.post("/api/node/promote"),
            client.post(
                "/api/node/memory/request",
                json={
                    "key": "user:test",
                    "value": "secret",
                    "source": {"node_id": "node-b"},
                },
            ),
            client.post(
                "/api/memory/sync",
                json={"dry_run": True, "confirm": False},
            ),
        ]

    assert all(response.status_code == 401 for response in responses)


def test_explicit_testing_and_loopback_paths_allow_unsigned_requests():
    payload = {"node_id": "node-b", "role": "secondary"}

    with TestClient(_app(secret="", testing=True)) as testing_client:
        testing_response = testing_client.post(
            "/api/node/heartbeat",
            json=payload,
        )

    with TestClient(
        _app(secret="", allow_loopback=True),
        client=("127.0.0.1", 50000),
    ) as loopback_client:
        loopback_response = loopback_client.post(
            "/api/node/heartbeat",
            json=payload,
        )

    assert testing_response.status_code == 200
    assert loopback_response.status_code == 200


def test_sensitive_payload_limit_is_enforced():
    app = _app(testing=True, max_body_bytes=1024)

    with TestClient(app) as client:
        response = client.post(
            "/api/node/memory/request",
            json={
                "key": "user:test",
                "value": "x" * 2048,
                "source": {"node_id": "node-b"},
            },
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "lan_payload_too_large"
