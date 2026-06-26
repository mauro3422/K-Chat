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


def action_doctor(profile: NodeProfile) -> int:
    print(f"node={profile.name}")
    print(f"target={profile.target}")
    print(f"repo={profile.repo}")
    print(f"identity={profile.identity_file}")
    print(f"url={profile.base_url}")
    checks = [
        ("ssh", "printf 'ssh=ok\\n'; uname -a"),
        ("repo", f"test -d {bash_quote(profile.repo)} && cd {bash_quote(profile.repo)} && git status --short --branch"),
        ("script", f"test -x {bash_quote(profile.repo)}/scripts/kairos-node.sh && echo script=ok"),
        ("python", f"cd {bash_quote(profile.repo)} && (venv/bin/python --version || .venv/bin/python --version || python3 --version)"),
        ("health", remote_script(profile, "health")),
        ("platform", remote_script(profile, "platform")),
    ]
    failed = 0
    for label, command in checks:
        print(f"\n[{label}]")
        result = capture_ssh(profile, command, timeout=30)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            failed += 1
            print(f"{label}=failed exit={result.returncode}", file=sys.stderr)
    return 1 if failed else 0


def action_http_get(profile: NodeProfile, path: str) -> int:
    url = profile.base_url + path
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            print(response.read().decode("utf-8", errors="replace"))
        return 0
    except urllib.error.URLError as exc:
        print(f"HTTP failed: {url}: {exc}", file=sys.stderr)
        return 1


def action_chat(profile: NodeProfile, message: str, *, session_id: str, model: str = "") -> int:
    if not message.strip():
        raise SystemExit("chat requires --message")
    params = urllib.parse.urlencode({"model": model}) if model else ""
    url = f"{profile.base_url}/chat/{urllib.parse.quote(session_id)}"
    if params:
        url += f"?{params}"
    body = urllib.parse.urlencode({"message": message}).encode("utf-8")
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
    parser.add_argument("action", choices=["list", "doctor", "health", "pull", "restart", "status", "logs", "platform", "exec", "chat"])
    parser.add_argument("--node", default=os.environ.get("KAIROS_REMOTE_NODE", "linux"))
    parser.add_argument("--config", default=os.environ.get("KAIROS_REMOTE_NODES_CONFIG", str(default_config_path())))
    parser.add_argument("--command", default="")
    parser.add_argument("--lines", type=int, default=150)
    parser.add_argument("--message", default="")
    parser.add_argument("--session-id", default=f"remote-cli-{int(time.time())}")
    parser.add_argument("--model", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profiles = load_profiles(Path(args.config))
    if args.action == "list":
        return action_list(profiles)
    profile = require_profile(profiles, args.node)
    if args.action == "doctor":
        return action_doctor(profile)
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
        return action_chat(profile, args.message, session_id=args.session_id, model=args.model)
    raise SystemExit(f"Unhandled action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main())
