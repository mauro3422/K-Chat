#!/usr/bin/env python
"""Two-node LAN field smoke test for Kairos.

This is intentionally an edge script: it talks to public HTTP endpoints from
RUNBOOK_LAN_SYNC.md and avoids importing app internals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True)
class Node:
    name: str
    url: str


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""
    node: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class Client:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def request(
        self,
        method: str,
        node: Node,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = node.url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise RuntimeError(f"expected JSON object, got {type(parsed).__name__}")
                return parsed
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {url}: {raw[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach {url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON from {url}: {exc}") from exc


def normalize_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value:
        raise ValueError("empty URL")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid URL: {raw}")
    return value


def short_json(data: Any, limit: int = 360) -> str:
    try:
        rendered = json.dumps(data, ensure_ascii=False, sort_keys=True)
    except TypeError:
        rendered = str(data)
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def expect(condition: bool, name: str, *, node: str = "", detail: str = "", data: dict[str, Any] | None = None) -> Step:
    return Step(name=name, ok=condition, node=node, detail=detail, data=data or {})


def get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def peer_ids(state: dict[str, Any]) -> set[str]:
    peers = state.get("peers", [])
    if not isinstance(peers, list):
        return set()
    return {str(peer.get("node_id", "")).strip() for peer in peers if isinstance(peer, dict)}


def find_primary(primary_state: dict[str, Any], secondary_state: dict[str, Any]) -> dict[str, Any]:
    if primary_state.get("role") == "primary":
        return primary_state
    if secondary_state.get("role") == "primary":
        return secondary_state
    return primary_state


def wait_for_snapshot_match(
    client: Client,
    node: Node,
    key: str,
    *,
    attempts: int,
    delay: float,
) -> tuple[bool, dict[str, Any]]:
    last: dict[str, Any] = {}
    for _ in range(attempts):
        last = client.request("GET", node, "/api/node/memory/snapshot", params={"key_pattern": key})
        compare = last.get("compare", {})
        if isinstance(compare, dict):
            if key not in compare.get("only_in_md", []) and key not in compare.get("only_in_db", []):
                if not compare.get("mismatched"):
                    return True, last
            if key in compare.get("only_in_md", []) or key in compare.get("only_in_db", []):
                time.sleep(delay)
                continue
        time.sleep(delay)
    return False, last


def run_smoke(args: argparse.Namespace) -> list[Step]:
    client = Client(timeout=args.timeout)
    primary = Node("primary", normalize_url(args.primary_url))
    secondary = Node("secondary", normalize_url(args.secondary_url))
    steps: list[Step] = []

    health: dict[str, dict[str, Any]] = {}
    states: dict[str, dict[str, Any]] = {}
    for node in (primary, secondary):
        try:
            health[node.name] = client.request("GET", node, "/health")
            steps.append(expect(health[node.name].get("status") == "ok", "health.status == ok", node=node.name, data=health[node.name]))
        except Exception as exc:
            steps.append(expect(False, "health reachable", node=node.name, detail=str(exc)))
            return steps

        try:
            states[node.name] = client.request("GET", node, "/api/node/state")
            steps.append(
                expect(
                    bool(states[node.name].get("node_id")) and states[node.name].get("healthy") is True,
                    "node state healthy with node_id",
                    node=node.name,
                    data=states[node.name],
                )
            )
        except Exception as exc:
            steps.append(expect(False, "node state reachable", node=node.name, detail=str(exc)))
            return steps

    primary_id = str(states["primary"].get("node_id", "")).strip()
    secondary_id = str(states["secondary"].get("node_id", "")).strip()
    steps.append(
        expect(
            bool(primary_id and secondary_id and primary_id != secondary_id),
            "distinct node ids",
            detail=f"primary={primary_id!r} secondary={secondary_id!r}",
        )
    )

    heartbeat_payloads = [
        (
            secondary,
            {
                "node_id": primary_id,
                "role": str(states["primary"].get("role") or "secondary"),
                "base_url": primary.url,
                "metadata": {"source": "lan_field_smoke"},
            },
        ),
        (
            primary,
            {
                "node_id": secondary_id,
                "role": str(states["secondary"].get("role") or "secondary"),
                "base_url": secondary.url,
                "metadata": {"source": "lan_field_smoke"},
            },
        ),
    ]
    for target, payload in heartbeat_payloads:
        try:
            response = client.request("POST", target, "/api/node/heartbeat", payload=payload)
            steps.append(expect(response.get("ok") is True, "heartbeat accepted", node=target.name, data=response))
        except Exception as exc:
            steps.append(expect(False, "heartbeat accepted", node=target.name, detail=str(exc)))

    states["primary"] = client.request("GET", primary, "/api/node/state")
    states["secondary"] = client.request("GET", secondary, "/api/node/state")
    steps.append(expect(secondary_id in peer_ids(states["primary"]), "primary recorded secondary heartbeat", node="primary", data=states["primary"]))
    steps.append(expect(primary_id in peer_ids(states["secondary"]), "secondary recorded primary heartbeat", node="secondary", data=states["secondary"]))

    sync_status: dict[str, dict[str, Any]] = {}
    failover_status: dict[str, dict[str, Any]] = {}
    for node in (primary, secondary):
        sync_status[node.name] = client.request("GET", node, "/api/node/sync/status")
        sync = sync_status[node.name].get("sync", {})
        cluster = sync_status[node.name].get("cluster", {})
        steps.append(expect(sync_status[node.name].get("ok") is True, "sync status ok", node=node.name, data=sync_status[node.name]))
        steps.append(expect(sync.get("memory_is_fresh") is True, "sync.memory_is_fresh == true", node=node.name, data=sync_status[node.name]))
        steps.append(expect(int(cluster.get("reachable_peers", 0)) >= 1, "cluster has reachable peer", node=node.name, data=sync_status[node.name]))

        failover_status[node.name] = client.request("GET", node, "/api/node/failover/status")
        steps.append(expect(failover_status[node.name].get("ok") is True, "failover status ok", node=node.name, data=failover_status[node.name]))
        steps.append(expect(failover_status[node.name].get("should_promote") is False, "failover should_promote == false", node=node.name, data=failover_status[node.name]))

    if args.skip_write:
        return steps

    probe_key = args.probe_key or f"lan_field_smoke:{int(time.time())}"
    probe_value = f"{args.probe_value} ({time.strftime('%Y-%m-%d %H:%M:%S')})"
    writer = primary if states["primary"].get("role") == "primary" else secondary
    reader = secondary if writer.name == "primary" else primary

    try:
        write_response = client.request(
            "POST",
            writer,
            "/api/node/memory/request",
            payload={
                "key": probe_key,
                "value": probe_value,
                "source": {"node_id": "lan-field-smoke", "role": "test", "base_url": ""},
            },
        )
        steps.append(expect(write_response.get("ok") is True and write_response.get("granted") is True, "memory write granted on primary", node=writer.name, data=write_response))
    except Exception as exc:
        steps.append(expect(False, "memory write granted on primary", node=writer.name, detail=str(exc)))
        return steps

    try:
        sync_response = client.request(
            "POST",
            writer,
            "/api/memory/sync",
            payload={"dry_run": False, "confirm": True, "key_pattern": probe_key, "fmt": "text"},
        )
        steps.append(expect(sync_response.get("ok") is True, "memory sync endpoint ok", node=writer.name, data=sync_response))
    except Exception as exc:
        steps.append(expect(False, "memory sync endpoint ok", node=writer.name, detail=str(exc)))

    matched, snapshot = wait_for_snapshot_match(client, reader, probe_key, attempts=args.sync_attempts, delay=args.sync_delay)
    source_mode = get_path(snapshot, "source.mode", "")
    steps.append(
        expect(
            matched,
            "secondary can see probe memory",
            node=reader.name,
            detail=f"source.mode={source_mode!r}",
            data=snapshot,
        )
    )
    steps.append(expect(get_path(snapshot, "memory.is_fresh", False) is True, "probe memory snapshot is fresh", node=reader.name, data=snapshot))

    if args.promote_secondary:
        target = secondary
        try:
            promote = client.request("POST", target, "/api/node/promote")
            role = get_path(promote, "state.role", "")
            steps.append(expect(promote.get("ok") is True and role == "primary", "manual failover promote secondary", node=target.name, data=promote))
        except Exception as exc:
            steps.append(expect(False, "manual failover promote secondary", node=target.name, detail=str(exc)))
    else:
        steps.append(expect(True, "manual failover promote secondary skipped", detail="use --promote-secondary to execute it"))

    if not args.keep_probe:
        try:
            cleanup = client.request(
                "POST",
                writer,
                "/api/node/memory/request",
                payload={
                    "key": probe_key,
                    "value": "",
                    "source": {"node_id": "lan-field-smoke", "role": "test", "base_url": ""},
                },
            )
            steps.append(expect(cleanup.get("ok") is True, "probe cleanup requested", node=writer.name, data=cleanup))
        except Exception as exc:
            steps.append(expect(False, "probe cleanup requested", node=writer.name, detail=str(exc)))

    return steps


def print_report(steps: list[Step]) -> None:
    failures = [step for step in steps if not step.ok]
    passed = len(steps) - len(failures)
    print(f"LAN field smoke: {passed}/{len(steps)} checks passed")
    if not failures:
        print("OK: health, node state, heartbeats, sync, memory visibility and failover status passed.")
        return

    print("")
    print("Failures:")
    for step in failures:
        prefix = f"- {step.name}"
        if step.node:
            prefix += f" [{step.node}]"
        print(prefix)
        if step.detail:
            print(f"  detail: {step.detail}")
        if step.data:
            print(f"  data: {short_json(step.data)}")

    print("")
    print("Next checks:")
    print("- Confirm KAIROS_PEER_URLS points each node at the other LAN URL.")
    print("- Confirm both servers were restarted after .env or code changes.")
    print("- Inspect /health, /api/node/sync/status and /api/node/failover/status on the failing node.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Kairos two-node LAN field smoke test.")
    parser.add_argument(
        "urls",
        nargs="*",
        help="Optional positional URLs: [secondary-url] or [primary-url secondary-url]. Useful when npm filters long flags.",
    )
    parser.add_argument("--primary-url", default=os.getenv("KAIROS_LAN_PRIMARY_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--secondary-url", default=os.getenv("KAIROS_LAN_SECONDARY_URL", ""))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("KAIROS_LAN_SMOKE_TIMEOUT", DEFAULT_TIMEOUT)))
    parser.add_argument("--sync-attempts", type=int, default=int(os.getenv("KAIROS_LAN_SMOKE_SYNC_ATTEMPTS", "6")))
    parser.add_argument("--sync-delay", type=float, default=float(os.getenv("KAIROS_LAN_SMOKE_SYNC_DELAY", "1.0")))
    parser.add_argument("--probe-key", default=os.getenv("KAIROS_LAN_SMOKE_PROBE_KEY", ""))
    parser.add_argument("--probe-value", default=os.getenv("KAIROS_LAN_SMOKE_PROBE_VALUE", "LAN field smoke probe"))
    parser.add_argument("--skip-write", action="store_true", help="Skip the memory write/sync probe.")
    parser.add_argument("--keep-probe", action="store_true", help="Keep the probe memory entry after the run.")
    parser.add_argument("--promote-secondary", action="store_true", help="Actually POST /api/node/promote on the secondary node.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if len(args.urls) == 1:
        args.secondary_url = args.urls[0]
    elif len(args.urls) == 2:
        args.primary_url = args.urls[0]
        args.secondary_url = args.urls[1]
    elif len(args.urls) > 2:
        parser.error("expected at most two positional URLs: [secondary-url] or [primary-url secondary-url]")
    if not args.secondary_url:
        parser.error("--secondary-url is required, or set KAIROS_LAN_SECONDARY_URL")

    try:
        steps = run_smoke(args)
    except Exception as exc:
        steps = [expect(False, "smoke runner crashed", detail=str(exc))]
    print_report(steps)
    return 0 if all(step.ok for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
