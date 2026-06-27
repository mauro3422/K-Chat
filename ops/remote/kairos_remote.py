#!/usr/bin/env python
"""Kairos multi-node remote control client.

This is the portable core behind the Windows PowerShell wrapper. It deliberately
uses only the Python standard library so it can run before dependencies are
fully installed.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODEX_DELEGATION_GUIDE = """\
[Contexto operativo remoto]
Origen: Codex esta hablando con Kairos por el canal LAN/CLI para delegar una prueba, diagnostico o tarea tecnica.
Modo esperado:
- Responde breve, concreto y auditable.
- Si se pide una prueba, devuelve resultado, evidencia minima y causa probable si falla.
- No asumas que Mauro esta escribiendo directamente; puede ser Codex coordinando entre nodos.
- Si falta contexto o permisos, dilo y propone el siguiente comando o chequeo.
- No modifiques memoria, archivos ni configuracion salvo que el pedido lo diga de forma explicita.

[Mensaje delegado]
"""


@dataclass(frozen=True)
class NodeProfile:
    name: str
    host: str
    user: str
    repo: str
    identity_file: str
    port: int = 22
    service_url: str = ""

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"

    @property
    def base_url(self) -> str:
        return (self.service_url or f"http://{self.host}:8000").rstrip("/")


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str = ""
    hint: str = ""
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "hint": self.hint,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def _expand_path(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    return repo_root() / ".kairos" / "remote-nodes.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"config must be a JSON object: {path}")
    return data


def _profile_from_mapping(name: str, raw: dict[str, Any]) -> NodeProfile:
    return NodeProfile(
        name=name,
        host=str(raw.get("host", "")).strip(),
        user=str(raw.get("user", "")).strip(),
        repo=str(raw.get("repo", "")).strip(),
        identity_file=_expand_path(str(raw.get("identity_file") or raw.get("identityFile") or "")),
        port=int(raw.get("port") or 22),
        service_url=str(raw.get("service_url") or raw.get("serviceUrl") or "").strip(),
    )


def fallback_profile(name: str = "linux") -> NodeProfile:
    return NodeProfile(
        name=name,
        host=os.environ.get("KAIROS_LINUX_HOST", "").strip(),
        user=os.environ.get("KAIROS_LINUX_USER", "").strip(),
        repo=os.environ.get("KAIROS_LINUX_REPO", "").strip(),
        identity_file=_expand_path(os.environ.get("KAIROS_LINUX_IDENTITY", r"~/.ssh/kairos_linux_ed25519")),
        port=int(os.environ.get("KAIROS_LINUX_SSH_PORT", "22") or 22),
        service_url=os.environ.get("KAIROS_LINUX_BASE_URL", "").strip(),
    )


def load_profiles(config_path: Path) -> dict[str, NodeProfile]:
    profiles: dict[str, NodeProfile] = {}
    if config_path.exists():
        data = _load_json(config_path)
        nodes = data.get("nodes", data)
        if not isinstance(nodes, dict):
            raise ValueError("remote nodes config must contain an object named 'nodes'")
        for name, raw in nodes.items():
            if isinstance(raw, dict):
                profiles[str(name)] = _profile_from_mapping(str(name), raw)
    fallback = fallback_profile()
    if fallback.host and fallback.user:
        profiles.setdefault(fallback.name, fallback)
    return profiles


def require_profile(profiles: dict[str, NodeProfile], name: str) -> NodeProfile:
    if name in profiles:
        profile = profiles[name]
    elif len(profiles) == 1:
        profile = next(iter(profiles.values()))
    else:
        available = ", ".join(sorted(profiles)) or "none"
        raise SystemExit(f"Unknown node '{name}'. Available nodes: {available}. Config: {default_config_path()}")

    missing = [field for field in ("host", "user", "repo", "identity_file") if not getattr(profile, field)]
    if missing:
        raise SystemExit(f"Node '{profile.name}' is missing: {', '.join(missing)}")
    if not Path(profile.identity_file).exists():
        raise SystemExit(f"Identity file not found for node '{profile.name}': {profile.identity_file}")
    return profile


def bash_quote(value: str) -> str:
    return shlex.quote(value)


def ssh_args(profile: NodeProfile) -> list[str]:
    return [
        "ssh",
        "-i",
        profile.identity_file,
        "-p",
        str(profile.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=accept-new",
        profile.target,
    ]


def run_ssh(profile: NodeProfile, command: str, *, timeout: int | None = None) -> int:
    result = subprocess.run([*ssh_args(profile), command], text=True, timeout=timeout)
    return result.returncode


def capture_ssh(profile: NodeProfile, command: str, *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ssh_args(profile), command], text=True, capture_output=True, timeout=timeout)


def remote_script(profile: NodeProfile, action: str) -> str:
    return f"cd {bash_quote(profile.repo)} && ./scripts/kairos-node.sh {action}"


def action_list(profiles: dict[str, NodeProfile]) -> int:
    for name in sorted(profiles):
        profile = profiles[name]
        print(f"{name}\thost={profile.host}\tuser={profile.user}\trepo={profile.repo}\turl={profile.base_url}")
    return 0


def doctor_hint(name: str, detail: str = "", stdout: str = "", stderr: str = "") -> str:
    text = f"{name} {detail} {stdout} {stderr}".lower()
    if name == "profile":
        return "Revisar .kairos/remote-nodes.json o variables KAIROS_LINUX_*."
    if "permission denied" in text or "publickey" in text:
        return "SSH no autentica: revisar identityFile, permisos de la clave y authorized_keys del nodo."
    if "could not resolve" in text or "timed out" in text or "connection refused" in text or "no route" in text:
        return "No hay conexion al nodo: revisar IP, red LAN, puerto SSH/firewall y que la laptop este encendida."
    if name == "repo":
        return "Repo remoto no esta listo: revisar ruta repo, rama, git status y conflictos locales."
    if name == "script":
        return "Falta scripts/kairos-node.sh ejecutable: hacer git pull y chmod +x si corresponde."
    if name == "python":
        return "Python/venv remoto no esta listo: revisar venv, version Python y dependencias."
    if name == "health":
        return "Kairos HTTP no esta sano: revisar servicio, puerto 8000, .env y logs."
    if name == "node_state":
        return "El nodo no expone estado LAN: revisar KAIROS_NODE_ID/KAIROS_NODE_ROLE y reiniciar."
    if name == "sync_status":
        return "La sync LAN no esta sana: revisar KAIROS_PEER_URLS, memoria fresca y cola pendiente."
    if name == "failover_status":
        return "Failover dudoso: revisar lease de liderazgo, misses de heartbeat y rol configurado."
    return "Revisar salida del check y repetir doctor despues de corregir."


def _short(text: str, limit: int = 1200) -> str:
    clean = text.strip()
    return clean if len(clean) <= limit else clean[: limit - 3] + "..."


def _ssh_check(profile: NodeProfile, name: str, command: str, *, timeout: int = 30) -> DoctorCheck:
    try:
        result = capture_ssh(profile, command, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        detail = f"timeout after {exc.timeout}s"
        return DoctorCheck(name=name, ok=False, detail=detail, hint=doctor_hint(name, detail))
    except OSError as exc:
        detail = str(exc)
        return DoctorCheck(name=name, ok=False, detail=detail, hint=doctor_hint(name, detail))
    stdout = _short(result.stdout or "")
    stderr = _short(result.stderr or "")
    ok = result.returncode == 0
    detail = "ok" if ok else f"exit={result.returncode}"
    return DoctorCheck(name=name, ok=ok, detail=detail, hint="" if ok else doctor_hint(name, detail, stdout, stderr), stdout=stdout, stderr=stderr)


def _http_check(profile: NodeProfile, name: str, path: str, *, timeout: float = 8) -> DoctorCheck:
    url = profile.base_url + path
    try:
        data = _http_json(profile, path, timeout=timeout)
    except Exception as exc:
        detail = f"{url}: {exc}"
        return DoctorCheck(name=name, ok=False, detail=detail, hint=doctor_hint(name, detail))
    ok = bool(data.get("ok", True))
    if name == "health":
        ok = data.get("status") == "ok"
    if name == "node_state":
        ok = bool(data.get("node_id")) and data.get("healthy") is True
    if name == "sync_status":
        ok = data.get("ok") is True and data.get("sync", {}).get("memory_is_fresh") is True
    if name == "failover_status":
        ok = data.get("ok") is True and data.get("should_promote") is False
    rendered = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return DoctorCheck(name=name, ok=ok, detail="ok" if ok else "unexpected response", hint="" if ok else doctor_hint(name, stdout=rendered), stdout=_short(rendered))


def collect_doctor_checks(profile: NodeProfile) -> list[DoctorCheck]:
    checks = [
        DoctorCheck(
            name="profile",
            ok=bool(profile.host and profile.user and profile.repo and profile.identity_file and Path(profile.identity_file).exists()),
            detail=f"target={profile.target} repo={profile.repo} url={profile.base_url}",
            hint="" if Path(profile.identity_file).exists() else doctor_hint("profile"),
        ),
        _ssh_check(profile, "ssh", "printf 'ssh=ok\\n'; uname -a", timeout=20),
        _ssh_check(profile, "repo", f"test -d {bash_quote(profile.repo)} && cd {bash_quote(profile.repo)} && git status --short --branch", timeout=30),
        _ssh_check(profile, "script", f"test -x {bash_quote(profile.repo)}/scripts/kairos-node.sh && echo script=ok", timeout=20),
        _ssh_check(profile, "python", f"cd {bash_quote(profile.repo)} && (venv/bin/python --version || .venv/bin/python --version || python3 --version)", timeout=20),
        _http_check(profile, "health", "/health"),
        _http_check(profile, "node_state", "/api/node/state"),
        _http_check(profile, "sync_status", "/api/node/sync/status"),
        _http_check(profile, "failover_status", "/api/node/failover/status"),
    ]
    return checks


def print_doctor_report(profile: NodeProfile, checks: list[DoctorCheck]) -> None:
    failed = [check for check in checks if not check.ok]
    print(f"Kairos remote doctor: {len(checks) - len(failed)}/{len(checks)} checks passed")
    print(f"node={profile.name} target={profile.target} repo={profile.repo} url={profile.base_url}")
    for check in checks:
        status = "OK" if check.ok else "FAIL"
        print(f"\n[{status}] {check.name}: {check.detail}")
        if check.stdout:
            print(check.stdout)
        if check.stderr:
            print(check.stderr, file=sys.stderr)
        if check.hint:
            print(f"likely: {check.hint}")
    if failed:
        print("\nNext checks:")
        print("- Ejecutar doctor despues de corregir el primer FAIL de la lista.")
        print("- Si falla health pero SSH funciona, revisar logs/restart del servicio Kairos.")
        print("- Si falla sync/failover, revisar KAIROS_PEER_URLS y correr scripts/lan_field_smoke.py.")


def action_doctor(profile: NodeProfile, *, json_output: bool = False) -> int:
    checks = collect_doctor_checks(profile)
    failed = [check for check in checks if not check.ok]
    if json_output:
        payload = {
            "ok": not failed,
            "node": profile.name,
            "target": profile.target,
            "repo": profile.repo,
            "url": profile.base_url,
            "passed": len(checks) - len(failed),
            "total": len(checks),
            "checks": [check.to_dict() for check in checks],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_doctor_report(profile, checks)
    return 1 if failed else 0


def action_http_get(profile: NodeProfile, path: str, *, timeout: float = 12) -> int:
    url = profile.base_url + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            print(response.read().decode("utf-8", errors="replace"))
        return 0
    except urllib.error.URLError as exc:
        print(f"HTTP failed: {url}: {exc}", file=sys.stderr)
        return 1


def _http_json(profile: NodeProfile, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 20) -> dict[str, Any]:
    url = profile.base_url + path
    data = None
    method = "GET"
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"unexpected JSON response from {url}")
    return parsed


def action_task_create(profile: NodeProfile, *, title: str, message: str, session_id: str = "", priority: str = "normal") -> int:
    if not title.strip():
        raise SystemExit("task-create requires --title")
    if not message.strip():
        raise SystemExit("task-create requires --message")
    payload = {
        "title": title,
        "prompt": message,
        "session_id": session_id,
        "priority": priority,
        "from_node": os.environ.get("KAIROS_NODE_ID", "codex-remote-client"),
    }
    try:
        data = _http_json(profile, "/api/codex/tasks", payload)
    except Exception as exc:
        print(f"Task create failed: {exc}", file=sys.stderr)
        return 1
    task = data.get("task", {})
    print(f"created {task.get('id')} status={task.get('status')} title={task.get('title')}")
    return 0


def action_task_list(profile: NodeProfile, *, status: str = "open", lines: int = 50) -> int:
    path = f"/api/codex/tasks?{urllib.parse.urlencode({'status': status, 'limit': int(lines)})}"
    try:
        data = _http_json(profile, path)
    except Exception as exc:
        print(f"Task list failed: {exc}", file=sys.stderr)
        return 1
    tasks = data.get("tasks", [])
    if not tasks:
        print("No tasks.")
        return 0
    for task in tasks:
        print(f"{task.get('id')}\t{task.get('status')}\t{task.get('priority')}\t{task.get('title')}")
    return 0


def action_task_show(profile: NodeProfile, *, task_id: str) -> int:
    if not task_id:
        raise SystemExit("task-show requires --task-id")
    try:
        data = _http_json(profile, f"/api/codex/tasks/{urllib.parse.quote(task_id)}")
    except Exception as exc:
        print(f"Task show failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data.get("task", data), ensure_ascii=False, indent=2))
    return 0


def action_task_update(profile: NodeProfile, *, task_id: str, status: str, message: str = "") -> int:
    if not task_id:
        raise SystemExit("task-update requires --task-id")
    if not status:
        raise SystemExit("task-update requires --status")
    payload = {"status": status, "message": message, "role": "codex", "source": "codex-remote-client", "claimed_by": "codex"}
    try:
        data = _http_json(profile, f"/api/codex/tasks/{urllib.parse.quote(task_id)}", payload)
    except Exception as exc:
        print(f"Task update failed: {exc}", file=sys.stderr)
        return 1
    task = data.get("task", {})
    print(f"updated {task.get('id')} status={task.get('status')}")
    return 0


def delegated_message(message: str, *, raw_message: bool = False) -> str:
    if raw_message:
        return message
    return CODEX_DELEGATION_GUIDE + message


def action_chat(
    profile: NodeProfile,
    message: str,
    *,
    session_id: str,
    model: str = "",
    raw_message: bool = False,
) -> int:
    if not message.strip():
        raise SystemExit("chat requires --message")
    params = urllib.parse.urlencode({"model": model}) if model else ""
    url = f"{profile.base_url}/chat/{urllib.parse.quote(session_id)}"
    if params:
        url += f"?{params}"
    body = urllib.parse.urlencode({"message": delegated_message(message, raw_message=raw_message)}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/x-ndjson"},
        method="POST",
    )
    print(f"node={profile.name} session={session_id}")
    had_error = False
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(line)
                    continue
                event_type = event.get("t")
                data = event.get("d", "")
                if event_type == "content":
                    print(str(data), end="", flush=True)
                elif event_type == "error":
                    had_error = True
                    print(f"\n[error] {data}", file=sys.stderr)
                elif event_type in {"done", "end"}:
                    break
            print()
        return 1 if had_error else 0
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return exc.code or 1
    except urllib.error.URLError as exc:
        print(f"Chat HTTP failed: {url}: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kairos remote multi-node control")
    parser.add_argument(
        "action",
        choices=[
            "list",
            "doctor",
            "health",
            "pull",
            "restart",
            "status",
            "logs",
            "platform",
            "exec",
            "chat",
            "task-create",
            "task-list",
            "task-show",
            "task-update",
        ],
    )
    parser.add_argument("--node", default=os.environ.get("KAIROS_REMOTE_NODE", "linux"))
    parser.add_argument("--config", default=os.environ.get("KAIROS_REMOTE_NODES_CONFIG", str(default_config_path())))
    parser.add_argument("--command", default="")
    parser.add_argument("--lines", type=int, default=150)
    parser.add_argument("--message", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--priority", default="normal")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--task-status", default="")
    parser.add_argument("--session-id", default=f"remote-cli-{int(time.time())}")
    parser.add_argument("--model", default="")
    parser.add_argument("--raw-message", action="store_true", help="send the message without Codex delegation context")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON for supported actions")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profiles = load_profiles(Path(args.config))
    if args.action == "list":
        return action_list(profiles)
    profile = require_profile(profiles, args.node)
    if args.action == "doctor":
        return action_doctor(profile, json_output=args.json)
    if args.action == "health":
        return action_http_get(profile, "/health")
    if args.action == "pull":
        return run_ssh(profile, f"cd {bash_quote(profile.repo)} && git pull --ff-only --autostash")
    if args.action == "restart":
        return run_ssh(profile, remote_script(profile, "restart"), timeout=60)
    if args.action == "status":
        return run_ssh(profile, remote_script(profile, "status"), timeout=30)
    if args.action == "logs":
        return run_ssh(profile, remote_script(profile, f"logs {int(args.lines)}"), timeout=30)
    if args.action == "platform":
        return run_ssh(profile, remote_script(profile, "platform"), timeout=30)
    if args.action == "exec":
        if not args.command:
            raise SystemExit("exec requires --command")
        return run_ssh(profile, args.command)
    if args.action == "chat":
        return action_chat(
            profile,
            args.message,
            session_id=args.session_id,
            model=args.model,
            raw_message=args.raw_message,
        )
    if args.action == "task-create":
        return action_task_create(profile, title=args.title, message=args.message, session_id=args.session_id, priority=args.priority)
    if args.action == "task-list":
        return action_task_list(profile, status=args.task_status or "open", lines=args.lines)
    if args.action == "task-show":
        return action_task_show(profile, task_id=args.task_id)
    if args.action == "task-update":
        return action_task_update(profile, task_id=args.task_id, status=args.task_status, message=args.message)
    raise SystemExit(f"Unhandled action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main())
