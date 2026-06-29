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
        "no_restore_memory_file": False,
        "loopback": False,
        "loopback_peer_id": "",
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
        ("GET", "primary", "/api/node/runtime"): {"ok": True, "mode": "normal"},
        ("GET", "secondary", "/api/node/runtime"): {"ok": True, "mode": "normal"},
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


def test_run_smoke_accepts_loopback_single_physical_node(monkeypatch):
    responses = common_responses()
    synthetic_peer = "node-a-loopback-secondary"
    loopback_state = healthy_state("node-a", "primary", synthetic_peer)
    responses.update({
        ("GET", "primary", "/api/node/state"): loopback_state,
        ("GET", "secondary", "/api/node/state"): loopback_state,
        ("GET", "primary", "/api/node/sync/status"): {
            "ok": True,
            "sync": {"memory_is_fresh": True},
            "cluster": {"reachable_peers": 0},
        },
        ("GET", "secondary", "/api/node/sync/status"): {
            "ok": True,
            "sync": {"memory_is_fresh": True},
            "cluster": {"reachable_peers": 0},
        },
    })
    fake = FakeClient(responses)
    monkeypatch.setattr(lan_field_smoke, "Client", lambda timeout: fake)

    steps = lan_field_smoke.run_smoke(smoke_args(loopback=True, secondary_url="http://primary:8000"))

    assert all(step.ok for step in steps)
    assert any(step.name == "loopback uses one physical node" for step in steps)
    assert any(step.name == "loopback recorded synthetic secondary heartbeat" for step in steps)
    assert ("POST", "primary", "/api/node/heartbeat") in fake.calls


def test_main_loopback_does_not_require_secondary_url(monkeypatch, capsys):
    monkeypatch.setattr(lan_field_smoke, "run_smoke", lambda args: [lan_field_smoke.Step(name=args.secondary_url, ok=True)])

    assert lan_field_smoke.main(["--loopback", "--primary-url", "http://primary:8000", "--skip-write"]) == 0

    captured = capsys.readouterr()
    assert "1/1 checks passed" in captured.out


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


def test_print_report_includes_memory_probe_summary(capsys):
    lan_field_smoke.print_report([
        lan_field_smoke.Step(name="health.status == ok", ok=True),
        lan_field_smoke.Step(
            name="memory probe observability",
            ok=True,
            data={
                "_summary": True,
                "writer": "primary",
                "reader": "secondary",
                "probe_key": "lan_field_smoke:1",
                "write_ms": 12.3,
                "reported_write_ms": 4.5,
                "sync_ms": 20.1,
                "visibility_ms": 100.0,
                "primary_queue_size": 0,
                "secondary_queue_size": 0,
                "primary_lease_active": False,
            },
        ),
    ])

    captured = capsys.readouterr()
    assert "Memory probe: primary -> secondary" in captured.out
    assert "key=lan_field_smoke:1" in captured.out
    assert "api_write=4.5ms" in captured.out


def test_run_smoke_collects_memory_observability_summary(monkeypatch):
    responses = common_responses()
    responses.update({
        ("POST", "primary", "/api/node/memory/request"): {"ok": True, "granted": True, "duration_ms": 3.0},
        ("POST", "primary", "/api/memory/sync"): {"ok": True},
        ("GET", "secondary", "/api/node/memory/snapshot"): {
            "source": {"mode": "peer"},
            "memory": {"is_fresh": True},
            "compare": {"only_in_md": [], "only_in_db": [], "mismatched": []},
        },
    })
    for node in ("primary", "secondary"):
        responses[("GET", node, "/api/node/sync/status")] = {
            "ok": True,
            "sync": {"memory_is_fresh": True},
            "cluster": {"reachable_peers": 1},
            "observability": {"queue_size": 0, "lease": {"active": False}},
        }
    fake = FakeClient(responses)
    monkeypatch.setattr(lan_field_smoke, "Client", lambda timeout: fake)

    steps = lan_field_smoke.run_smoke(smoke_args(skip_write=False, probe_key="lan_field_smoke:test"))
    summary = next(step for step in steps if step.name == "memory probe observability")

    assert all(step.ok for step in steps)
    assert summary.data["writer"] == "primary"
    assert summary.data["reader"] == "secondary"
    assert summary.data["reported_write_ms"] == 3.0
    assert summary.data["primary_queue_size"] == 0
    assert summary.data["secondary_queue_size"] == 0
