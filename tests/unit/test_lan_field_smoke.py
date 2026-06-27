from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import lan_field_smoke


class FakeClient:
    def __init__(self, responses: dict[tuple[str, str, str], dict]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []

    def request(
        self,
        method: str,
        node: lan_field_smoke.Node,
        path: str,
        *,
        payload: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> dict:
        key = (method, node.name, path)
        self.calls.append(key)
        if key not in self.responses:
            raise RuntimeError(f"missing fake response for {key}")
        response = self.responses[key]
        if isinstance(response, Exception):
            raise response
        return response


def smoke_args(**overrides):
    base = {
        "primary_url": "http://primary:8000",
        "secondary_url": "http://secondary:8000",
        "timeout": 0.1,
        "skip_write": True,
        "sync_attempts": 1,
        "sync_delay": 0.0,
        "probe_key": "",
        "probe_value": "probe",
        "promote_secondary": False,
        "keep_probe": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def healthy_state(node_id: str, role: str, peer_id: str = "") -> dict:
    peers = [{"node_id": peer_id, "role": "secondary" if role == "primary" else "primary"}] if peer_id else []
    return {
        "node_id": node_id,
        "role": role,
        "healthy": True,
        "memory_is_fresh": True,
        "peers": peers,
    }


def common_responses(primary_role: str = "primary", secondary_role: str = "secondary") -> dict[tuple[str, str, str], dict]:
    primary_id = "node-a"
    secondary_id = "node-b"
    return {
        ("GET", "primary", "/health"): {"status": "ok"},
        ("GET", "secondary", "/health"): {"status": "ok"},
        ("GET", "primary", "/api/node/state"): healthy_state(primary_id, primary_role, secondary_id),
        ("GET", "secondary", "/api/node/state"): healthy_state(secondary_id, secondary_role, primary_id),
        ("POST", "primary", "/api/node/heartbeat"): {"ok": True},
        ("POST", "secondary", "/api/node/heartbeat"): {"ok": True},
        ("GET", "primary", "/api/node/sync/status"): {
            "ok": True,
            "sync": {"memory_is_fresh": True},
            "cluster": {"reachable_peers": 1},
        },
        ("GET", "secondary", "/api/node/sync/status"): {
            "ok": True,
            "sync": {"memory_is_fresh": True},
            "cluster": {"reachable_peers": 1},
        },
        ("GET", "primary", "/api/node/failover/status"): {"ok": True, "should_promote": False},
        ("GET", "secondary", "/api/node/failover/status"): {"ok": True, "should_promote": False},
    }


def test_run_smoke_accepts_healthy_two_node_topology(monkeypatch):
    fake = FakeClient(common_responses())
    monkeypatch.setattr(lan_field_smoke, "Client", lambda timeout: fake)

    steps = lan_field_smoke.run_smoke(smoke_args())

    assert all(step.ok for step in steps)
    assert any(step.name == "topology has one primary and one secondary" for step in steps)


def test_run_smoke_reports_inverted_urls(monkeypatch):
    fake = FakeClient(common_responses(primary_role="secondary", secondary_role="primary"))
    monkeypatch.setattr(lan_field_smoke, "Client", lambda timeout: fake)

    steps = lan_field_smoke.run_smoke(smoke_args())
    failed = [step for step in steps if not step.ok]

    assert any(step.name == "provided URLs match primary/secondary roles" for step in failed)
    assert any("URLs estan invertidas" in step.hint for step in failed)


def test_request_step_adds_actionable_hint():
    client = FakeClient({("GET", "primary", "/health"): RuntimeError("connection refused")})
    node = lan_field_smoke.Node("primary", "http://primary:8000")

    payload, failure = lan_field_smoke.request_step(client, "GET", node, "/health", "health reachable")

    assert payload is None
    assert failure is not None
    assert failure.ok is False
    assert "IP/puerto" in failure.hint


def test_print_report_includes_likely_hint(capsys):
    lan_field_smoke.print_report([
        lan_field_smoke.Step(
            name="heartbeat accepted",
            ok=False,
            node="secondary",
            detail="timed out",
            hint="Revisar KAIROS_PEER_URLS.",
        )
    ])

    captured = capsys.readouterr()
    assert "likely: Revisar KAIROS_PEER_URLS." in captured.out
