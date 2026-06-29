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


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    expected_node_id: str = ""
    expected_role: str = ""
    aliases: tuple[str, ...] = ()

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
    aliases = raw.get("aliases", ())
    if isinstance(aliases, str):
        aliases = (aliases,)
    elif isinstance(aliases, list):
        aliases = tuple(str(alias).strip() for alias in aliases if str(alias).strip())
    else:
        aliases = ()
    return NodeProfile(
        name=name,
        host=str(raw.get("host", "")).strip(),
        user=str(raw.get("user", "")).strip(),
        repo=str(raw.get("repo", "")).strip(),
        identity_file=_expand_path(str(raw.get("identity_file") or raw.get("identityFile") or "")),
        port=int(raw.get("port") or 22),
        service_url=str(raw.get("service_url") or raw.get("serviceUrl") or "").strip(),
        expected_node_id=str(raw.get("expected_node_id") or raw.get("expectedNodeId") or "").strip(),
        expected_role=str(raw.get("expected_role") or raw.get("expectedRole") or "").strip(),
        aliases=aliases,
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
        expected_node_id=os.environ.get("KAIROS_LINUX_EXPECTED_NODE_ID", "").strip(),
        expected_role=os.environ.get("KAIROS_LINUX_EXPECTED_ROLE", "secondary").strip(),
        aliases=("laptop", "secondary"),
    )


def load_profiles(config_path: Path) -> dict[str, NodeProfile]:
    profiles: dict[str, NodeProfile] = {}
    aliases: dict[str, NodeProfile] = {}
    if config_path.exists():
        data = _load_json(config_path)
        nodes = data.get("nodes", data)
        if not isinstance(nodes, dict):
            raise ValueError("remote nodes config must contain an object named 'nodes'")
        for name, raw in nodes.items():
            if isinstance(raw, dict):
                profile = _profile_from_mapping(str(name), raw)
                profiles[str(name)] = profile
                for alias in profile.aliases:
                    aliases.setdefault(alias, profile)
    fallback = fallback_profile()
    if fallback.host and fallback.user:
        profile = profiles.setdefault(fallback.name, fallback)
        for alias in fallback.aliases:
            aliases.setdefault(alias, profile)
    for alias, profile in aliases.items():
        profiles.setdefault(alias, profile)
    return profiles


def require_profile(profiles: dict[str, NodeProfile], name: str) -> NodeProfile:
    if name in profiles:
        profile = profiles[name]
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


def remote_python_bootstrap() -> str:
    return (
        'KAIROS_PY="$(if [ -x venv/bin/python ]; then printf %s venv/bin/python; '
        'elif [ -x .venv/bin/python ]; then printf %s .venv/bin/python; '
        'else command -v python3; fi)"'
    )


def remote_python_command(profile: NodeProfile, args: str = "") -> str:
    suffix = f" {args}" if args else ""
    return f"cd {bash_quote(profile.repo)} && {remote_python_bootstrap()} && \"$KAIROS_PY\"{suffix}"


def action_list(profiles: dict[str, NodeProfile]) -> int:
    seen: set[int] = set()
    for name in sorted(profiles):
        profile = profiles[name]
        marker = id(profile)
        if marker in seen:
            continue
        seen.add(marker)
        alias_names = sorted(alias for alias, candidate in profiles.items() if candidate is profile and alias != profile.name)
        alias_text = f"\taliases={','.join(alias_names)}" if alias_names else ""
        expected = []
        if profile.expected_node_id:
            expected.append(f"node_id={profile.expected_node_id}")
        if profile.expected_role:
            expected.append(f"role={profile.expected_role}")
        expected_text = f"\texpected={','.join(expected)}" if expected else ""
        print(f"{profile.name}\thost={profile.host}\tuser={profile.user}\trepo={profile.repo}\turl={profile.base_url}{alias_text}{expected_text}")
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
    if name == "node_runtime":
        return "El runtime del nodo no esta normal: revisar modo, reasons, peers y cola de memoria."
    if name == "sync_status":
        return "La sync LAN no esta sana: revisar KAIROS_PEER_URLS, memoria fresca y cola pendiente."
    if name == "failover_status":
        return "Failover dudoso: revisar lease de liderazgo, misses de heartbeat y rol configurado."
    if name == "memory_audit" or name.endswith("_memory_audit"):
        return "Auditoria de memoria fallo: revisar sesiones/vectores/catalogos y correr scripts/memory_audit.py para ver el detalle."
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
    attempts = 3 if name in {"node_runtime", "sync_status", "failover_status"} else 1
    last_check: DoctorCheck | None = None
    for attempt in range(attempts):
        try:
            data = _http_json(profile, path, timeout=timeout)
        except Exception as exc:
            detail = f"{url}: {exc}"
            last_check = DoctorCheck(name=name, ok=False, detail=detail, hint=doctor_hint(name, detail))
        else:
            ok = bool(data.get("ok", True))
            if name == "health":
                ok = data.get("status") == "ok"
            if name == "node_state":
                ok = bool(data.get("node_id")) and data.get("healthy") is True
                expected_errors = _node_identity_errors(profile, data)
                if expected_errors:
                    ok = False
            if name == "node_runtime":
                ok = data.get("mode") == "normal"
            if name == "sync_status":
                ok = data.get("ok") is True and data.get("sync", {}).get("memory_is_fresh") is True
            if name == "failover_status":
                ok = data.get("ok") is True and data.get("should_promote") is False
            rendered = json.dumps(data, ensure_ascii=False, sort_keys=True)
            detail = "ok" if ok else "unexpected response"
            if name == "node_state" and not ok:
                expected_errors = _node_identity_errors(profile, data)
                if expected_errors:
                    detail = "; ".join(expected_errors)
            last_check = DoctorCheck(name=name, ok=ok, detail=detail, hint="" if ok else doctor_hint(name, stdout=rendered), stdout=_short(rendered))
        if last_check.ok or attempt == attempts - 1:
            return last_check
        time.sleep(1)
    raise AssertionError("unreachable")


def _node_identity_errors(profile: NodeProfile, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if profile.expected_node_id and data.get("node_id") != profile.expected_node_id:
        errors.append(f"expected node_id={profile.expected_node_id} got {data.get('node_id')}")
    if profile.expected_role and data.get("role") != profile.expected_role:
        errors.append(f"expected role={profile.expected_role} got {data.get('role')}")
    return errors


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
        _ssh_check(
            profile,
            "python",
            remote_python_command(
                profile,
                "--version && \"$KAIROS_PY\" -c \"import fastembed; print('fastembed=ok')\"",
            ),
            timeout=20,
        ),
        _ssh_check(profile, "memory_audit", remote_python_command(profile, "scripts/memory_audit.py"), timeout=60),
        _http_check(profile, "health", "/health"),
        _http_check(profile, "node_state", "/api/node/state"),
        _http_check(profile, "node_runtime", "/api/node/runtime"),
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
    except Exception as exc:
        print(f"HTTP failed: {url}: {exc}", file=sys.stderr)
        return 1


def action_kairos_python(profile: NodeProfile, command: str) -> int:
    if not command.strip():
        raise SystemExit("kairos-python requires --command, for example: --command \"scripts/memory_audit.py\"")
    return run_ssh(profile, remote_python_command(profile, command))


@dataclass(frozen=True)
class RemotePythonJsonRunner:
    profile: NodeProfile

    def run_json(self, command: str, *, timeout: int) -> dict[str, Any]:
        result = capture_ssh(self.profile, remote_python_command(self.profile, command), timeout=timeout)
        if result.returncode != 0:
            message = f"remote exit={result.returncode}"
            if result.stdout.strip():
                message += f" stdout={_short(result.stdout)}"
            if result.stderr.strip():
                message += f" stderr={_short(result.stderr)}"
            raise RuntimeError(message)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"remote returned non-JSON output: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("remote returned JSON that is not an object")
        return payload


def action_memory_preflight(profile: NodeProfile, *, json_output: bool = False, dry_run: bool = False) -> int:
    from scripts.memory_pipeline_preflight import (
        build_pipeline_report,
        print_short_report,
        run_local_pipeline,
        run_remote_pipeline,
    )

    local = run_local_pipeline(node=os.environ.get("KAIROS_NODE_ID", "local"), dry_run=dry_run)
    remote = run_remote_pipeline(
        node=profile.name,
        runner=RemotePythonJsonRunner(profile),
        dry_run=dry_run,
    )
    report = build_pipeline_report([local, remote])
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_short_report(report)
    return 0 if report["ok"] else 2


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


def _http_json_url(url: str, *, timeout: float = 20) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"unexpected JSON response from {url}")
    return parsed


def _local_command_check(name: str, command: list[str], *, timeout: int = 30) -> DoctorCheck:
    try:
        result = subprocess.run(command, cwd=repo_root(), text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        detail = f"timeout after {exc.timeout}s"
        return DoctorCheck(name=name, ok=False, detail=detail, hint="El comando local no termino a tiempo.")
    except OSError as exc:
        detail = str(exc)
        return DoctorCheck(name=name, ok=False, detail=detail, hint="No se pudo ejecutar el comando local.")
    stdout = _short(result.stdout or "")
    stderr = _short(result.stderr or "")
    ok = result.returncode == 0
    detail = "ok" if ok else f"exit={result.returncode}"
    return DoctorCheck(name=name, ok=ok, detail=detail, hint="" if ok else "Revisar repo local y salida del comando.", stdout=stdout, stderr=stderr)


def _local_http_check(
    name: str,
    base_url: str,
    path: str,
    *,
    timeout: float = 8,
    expected_node_id: str = "",
    expected_role: str = "",
) -> DoctorCheck:
    url = base_url.rstrip("/") + path
    try:
        data = _http_json_url(url, timeout=timeout)
    except Exception as exc:
        detail = f"{url}: {exc}"
        return DoctorCheck(name=name, ok=False, detail=detail, hint="El nodo local no responde por HTTP: revisar servicio, IP/puerto y firewall.")
    ok = bool(data.get("ok", True))
    if name == "local_health":
        ok = data.get("status") == "ok"
    if name == "local_node_state":
        ok = bool(data.get("node_id")) and data.get("healthy") is True
        expected_errors = _expected_identity_errors(
            expected_node_id=expected_node_id,
            expected_role=expected_role,
            data=data,
        )
        if expected_errors:
            ok = False
    if name == "local_runtime":
        ok = data.get("mode") == "normal"
    rendered = json.dumps(data, ensure_ascii=False, sort_keys=True)
    detail = "ok" if ok else "unexpected response"
    if name == "local_node_state" and not ok:
        expected_errors = _expected_identity_errors(
            expected_node_id=expected_node_id,
            expected_role=expected_role,
            data=data,
        )
        if expected_errors:
            detail = "; ".join(expected_errors)
    return DoctorCheck(name=name, ok=ok, detail=detail, hint="" if ok else "El nodo local responde pero no esta en estado normal.", stdout=_short(rendered))


def _expected_identity_errors(*, expected_node_id: str, expected_role: str, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if expected_node_id and data.get("node_id") != expected_node_id:
        errors.append(f"expected node_id={expected_node_id} got {data.get('node_id')}")
    if expected_role and data.get("role") != expected_role:
        errors.append(f"expected role={expected_role} got {data.get('role')}")
    return errors


def _smoke_check(primary_url: str, secondary_url: str, *, loopback: bool = False, timeout: int = 180) -> DoctorCheck:
    command = [
        sys.executable,
        str(repo_root() / "scripts" / "lan_field_smoke.py"),
        "--primary-url",
        primary_url.rstrip("/"),
        "--sync-attempts",
        "4",
        "--sync-delay",
        "1",
    ]
    if loopback:
        command.append("--loopback")
        if secondary_url:
            command.extend(["--secondary-url", secondary_url.rstrip("/")])
    else:
        command.extend(["--secondary-url", secondary_url.rstrip("/")])
    try:
        result = subprocess.run(command, cwd=repo_root(), text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        detail = f"timeout after {exc.timeout}s"
        return DoctorCheck(name="lan_smoke", ok=False, detail=detail, hint="El smoke LAN quedo colgado: revisar locks de memoria y salud de ambos servicios.")
    stdout = _short(result.stdout or "", limit=2000)
    stderr = _short(result.stderr or "", limit=1200)
    ok = result.returncode == 0
    return DoctorCheck(
        name="lan_smoke",
        ok=ok,
        detail="ok" if ok else f"exit={result.returncode}",
        hint="" if ok else "Smoke LAN fallo: leer el reporte corto y corregir el primer failure.",
        stdout=stdout,
        stderr=stderr,
    )


def collect_lan_doctor_checks(profile: NodeProfile, *, primary_url: str, secondary_url: str, loopback: bool = False) -> list[DoctorCheck]:
    checks = [
        _local_command_check("local_git", ["git", "status", "--short", "--branch"]),
        _local_command_check("local_head", ["git", "rev-parse", "--short", "HEAD"]),
        _local_command_check("local_memory_audit", [sys.executable, "scripts/memory_audit.py"], timeout=60),
        _local_http_check("local_health", primary_url, "/health"),
        _local_http_check("local_node_state", primary_url, "/api/node/state", expected_role="primary"),
        _local_http_check("local_runtime", primary_url, "/api/node/runtime"),
    ]
    if loopback:
        checks.append(
            DoctorCheck(
                name="remote_doctor_skipped",
                ok=True,
                detail="loopback mode uses one physical node",
            )
        )
    else:
        checks.extend(
            DoctorCheck(
                name=f"remote_{check.name}",
                ok=check.ok,
                detail=check.detail,
                hint=check.hint,
                stdout=check.stdout,
                stderr=check.stderr,
            )
            for check in collect_doctor_checks(profile)
        )
    checks.append(_smoke_check(primary_url, secondary_url, loopback=loopback))
    return checks


def print_lan_doctor_report(profile: NodeProfile, checks: list[DoctorCheck], *, primary_url: str, secondary_url: str, loopback: bool = False) -> None:
    failed = [check for check in checks if not check.ok]
    print(f"Kairos LAN doctor: {len(checks) - len(failed)}/{len(checks)} checks passed")
    mode = "loopback" if loopback else "two-node"
    print(f"mode={mode} primary={primary_url.rstrip('/')} secondary={secondary_url.rstrip('/')} remote_node={profile.name}")
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
        print("- Corregir el primer FAIL; suele arrastrar los siguientes.")
        print("- Si remote_* falla pero local esta OK, correr doctor remoto del nodo.")
        print("- Si lan_smoke falla, revisar el reporte corto del smoke.")


def action_lan_doctor(profile: NodeProfile, *, primary_url: str, secondary_url: str, json_output: bool = False, loopback: bool = False) -> int:
    primary = primary_url.rstrip("/") or os.environ.get("KAIROS_LAN_PRIMARY_URL", "http://127.0.0.1:8000").rstrip("/")
    secondary = secondary_url.rstrip("/") or (primary if loopback else profile.base_url)
    checks = collect_lan_doctor_checks(profile, primary_url=primary, secondary_url=secondary, loopback=loopback)
    failed = [check for check in checks if not check.ok]
    if json_output:
        payload = {
            "ok": not failed,
            "mode": "loopback" if loopback else "two-node",
            "primary_url": primary,
            "secondary_url": secondary,
            "remote_node": profile.name,
            "passed": len(checks) - len(failed),
            "total": len(checks),
            "checks": [check.to_dict() for check in checks],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_lan_doctor_report(profile, checks, primary_url=primary, secondary_url=secondary, loopback=loopback)
    return 1 if failed else 0


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
            "lan-doctor",
            "memory-preflight",
            "preflight",
            "health",
            "pull",
            "restart",
            "status",
            "logs",
            "platform",
            "exec",
            "kairos-python",
            "chat",
            "task-create",
            "task-list",
            "task-show",
            "task-update",
        ],
    )
    parser.add_argument("--node", default=os.environ.get("KAIROS_REMOTE_NODE", "linux"))
    parser.add_argument("--config", default=os.environ.get("KAIROS_REMOTE_NODES_CONFIG", str(default_config_path())))
    parser.add_argument("--primary-url", default=os.environ.get("KAIROS_LAN_PRIMARY_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--secondary-url", default=os.environ.get("KAIROS_LAN_SECONDARY_URL", ""))
    parser.add_argument("--loopback", action="store_true", default=os.environ.get("KAIROS_LAN_SMOKE_LOOPBACK", "").lower() in {"1", "true", "yes", "on"})
    parser.add_argument("--dry-run", action="store_true", help="plan supported write steps without writing")
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
    if args.action in {"lan-doctor", "preflight"} and args.loopback:
        profile = profiles.get(args.node) or NodeProfile(
            name=args.node,
            host="",
            user="",
            repo="",
            identity_file="",
            service_url=args.secondary_url or args.primary_url,
        )
        return action_lan_doctor(profile, primary_url=args.primary_url, secondary_url=args.secondary_url, json_output=args.json, loopback=True)
    profile = require_profile(profiles, args.node)
    if args.action == "doctor":
        return action_doctor(profile, json_output=args.json)
    if args.action == "memory-preflight":
        return action_memory_preflight(profile, json_output=args.json, dry_run=args.dry_run)
    if args.action in {"lan-doctor", "preflight"}:
        return action_lan_doctor(profile, primary_url=args.primary_url, secondary_url=args.secondary_url, json_output=args.json, loopback=args.loopback)
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
    if args.action == "kairos-python":
        return action_kairos_python(profile, args.command)
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
