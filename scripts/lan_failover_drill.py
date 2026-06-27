#!/usr/bin/env python
"""Controlled two-node LAN failover drill for Kairos.

This script intentionally lives at the edge: it uses HTTP endpoints plus an
explicit local service stop/start command. It does not import app internals.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lan_field_smoke import (  # noqa: E402
    Client,
    Node,
    Step,
    expect,
    failure_hint,
    normalize_url,
    short_json,
    wait_for_snapshot_match,
)


DEFAULT_TIMEOUT = 30.0
DEFAULT_FAILOVER_TIMEOUT = 90.0
DEFAULT_RECOVERY_TIMEOUT = 90.0


def default_service_command(action: str) -> str:
    script = ROOT / "scripts" / "kairos-windows-service.ps1"
    if os.name == "nt":
        return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script}" -Action {action}'
    return ""


def run_command(command: str) -> tuple[bool, str]:
    if not command.strip():
        return False, "missing command"
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    return completed.returncode == 0, completed.stdout.strip()


def wait_until(
    name: str,
    check: Callable[[], tuple[bool, dict[str, Any] | str]],
    *,
    timeout: float,
    delay: float,
) -> Step:
    deadline = time.time() + timeout
    last: dict[str, Any] | str = {}
    while time.time() < deadline:
        try:
            ok, last = check()
            if ok:
                return expect(True, name, data=last if isinstance(last, dict) else {}, detail=last if isinstance(last, str) else "")
        except Exception as exc:
            last = str(exc)
        time.sleep(delay)
    detail = last if isinstance(last, str) else short_json(last)
    return expect(False, name, detail=detail, hint=failure_hint(name, detail, last if isinstance(last, dict) else None))


def run_drill(args: argparse.Namespace) -> list[Step]:
    client = Client(timeout=args.timeout)
    primary = Node("primary", normalize_url(args.primary_url))
    secondary = Node("secondary", normalize_url(args.secondary_url))
    steps: list[Step] = []
    primary_stopped = False
    primary_started = False

    try:
        primary_runtime = client.request("GET", primary, "/api/node/runtime")
        secondary_runtime = client.request("GET", secondary, "/api/node/runtime")
        steps.append(expect(primary_runtime.get("node", {}).get("role") == "primary", "primary starts as primary", node="primary", data=primary_runtime))
        steps.append(expect(secondary_runtime.get("node", {}).get("role") == "secondary", "secondary starts as secondary", node="secondary", data=secondary_runtime))

        if not args.allow_service_control:
            steps.append(expect(False, "service control explicitly allowed", detail="pass --allow-service-control to stop/start the primary"))
            return steps

        ok, output = run_command(args.stop_primary_command)
        primary_stopped = ok
        steps.append(expect(ok, "primary service stopped", node="primary", detail=output, hint="Revisar el comando --stop-primary-command."))
        if not ok:
            return steps

        def primary_unreachable() -> tuple[bool, dict[str, Any] | str]:
            try:
                payload = client.request("GET", primary, "/health")
            except Exception as exc:
                return True, str(exc)
            return False, payload

        step = wait_until("primary health unreachable", primary_unreachable, timeout=args.primary_down_timeout, delay=args.poll_delay)
        step.node = "primary"
        steps.append(step)
        if not step.ok:
            return steps

        def secondary_promoted() -> tuple[bool, dict[str, Any] | str]:
            payload = client.request("GET", secondary, "/api/node/runtime")
            role = payload.get("node", {}).get("role")
            write_mode = payload.get("memory", {}).get("write", {}).get("mode")
            ok = role == "primary" and write_mode == "temporary_primary_replay"
            return ok, payload

        step = wait_until("secondary promoted with replay mode", secondary_promoted, timeout=args.failover_timeout, delay=args.poll_delay)
        step.node = "secondary"
        steps.append(step)
        if not step.ok:
            return steps

        probe_key = args.probe_key or f"lan_failover_drill:{int(time.time())}"
        probe_value = f"{args.probe_value} ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        write_response = client.request(
            "POST",
            secondary,
            "/api/node/memory/request",
            payload={
                "key": probe_key,
                "value": probe_value,
                "source": {"node_id": "lan-failover-drill", "role": "test", "base_url": ""},
            },
        )
        steps.append(
            expect(
                write_response.get("ok") is True
                and write_response.get("granted") is True
                and write_response.get("replay_queued") is True,
                "failover memory write queued for replay",
                node="secondary",
                data=write_response,
                hint="La secondary promovida debe guardar local y dejar replay pendiente para el primary preferido.",
            )
        )

        ok, output = run_command(args.start_primary_command)
        primary_started = ok
        steps.append(expect(ok, "primary service started", node="primary", detail=output, hint="Revisar el comando --start-primary-command."))
        if not ok:
            return steps

        def primary_reachable() -> tuple[bool, dict[str, Any] | str]:
            payload = client.request("GET", primary, "/health")
            return payload.get("status") == "ok", payload

        step = wait_until("primary health restored", primary_reachable, timeout=args.recovery_timeout, delay=args.poll_delay)
        step.node = "primary"
        steps.append(step)
        if not step.ok:
            return steps

        def secondary_yielded() -> tuple[bool, dict[str, Any] | str]:
            payload = client.request("GET", secondary, "/api/node/runtime")
            role = payload.get("node", {}).get("role")
            mode = payload.get("mode")
            queue_size = int(payload.get("memory", {}).get("queue_size", 0) or 0)
            ok = role == "secondary" and mode == "normal" and queue_size == 0
            return ok, payload

        step = wait_until("secondary yielded and replay queue drained", secondary_yielded, timeout=args.recovery_timeout, delay=args.poll_delay)
        step.node = "secondary"
        steps.append(step)

        matched, snapshot = wait_for_snapshot_match(
            client,
            primary,
            probe_key,
            attempts=args.sync_attempts,
            delay=args.sync_delay,
        )
        steps.append(
            expect(
                matched,
                "primary can see failover probe memory",
                node="primary",
                data=snapshot,
                hint="Si falla, la memoria escrita durante failover no fue reemitida al primary preferido.",
            )
        )
    finally:
        if primary_stopped and not primary_started:
            ok, output = run_command(args.start_primary_command)
            steps.append(expect(ok, "primary service emergency start", node="primary", detail=output))

    return steps


def print_drill_report(steps: list[Step]) -> None:
    failures = [step for step in steps if not step.ok]
    passed = len(steps) - len(failures)
    print(f"LAN failover drill: {passed}/{len(steps)} checks passed")
    if not failures:
        print("OK: primary outage, secondary promotion, failover memory replay and recovery passed.")
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
        hint = step.hint or failure_hint(step.name, step.detail, step.data)
        if hint:
            print(f"  likely: {hint}")
        if step.data:
            print(f"  data: {short_json(step.data)}")

    print("")
    print("Next checks:")
    print("- Confirm the primary service is running again.")
    print("- Inspect /api/node/runtime on both nodes.")
    print("- Inspect /api/node/memory/queue on the secondary if replay did not drain.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a controlled Kairos LAN failover drill.")
    parser.add_argument("--primary-url", default=os.getenv("KAIROS_LAN_PRIMARY_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--secondary-url", default=os.getenv("KAIROS_LAN_SECONDARY_URL", ""))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("KAIROS_LAN_DRILL_TIMEOUT", DEFAULT_TIMEOUT)))
    parser.add_argument("--failover-timeout", type=float, default=DEFAULT_FAILOVER_TIMEOUT)
    parser.add_argument("--recovery-timeout", type=float, default=DEFAULT_RECOVERY_TIMEOUT)
    parser.add_argument("--primary-down-timeout", type=float, default=20.0)
    parser.add_argument("--poll-delay", type=float, default=2.0)
    parser.add_argument("--sync-attempts", type=int, default=10)
    parser.add_argument("--sync-delay", type=float, default=2.0)
    parser.add_argument("--probe-key", default="")
    parser.add_argument("--probe-value", default="LAN failover drill probe")
    parser.add_argument("--allow-service-control", action="store_true", help="Required to stop/start the primary service.")
    parser.add_argument("--stop-primary-command", default=default_service_command("Stop"))
    parser.add_argument("--start-primary-command", default=default_service_command("Start"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.secondary_url:
        parser.error("--secondary-url is required, or set KAIROS_LAN_SECONDARY_URL")
    steps = run_drill(args)
    print_drill_report(steps)
    return 0 if all(step.ok for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
