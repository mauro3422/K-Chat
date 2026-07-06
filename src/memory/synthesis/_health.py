from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from src.memory import paths as memory_paths


_project_root = memory_paths._project_root


def _base(root: str | Path | None = None) -> Path:
    return Path(root) if root is not None else _project_root()


def _run_command(args: list[str], cwd: Path, timeout: int = 8) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except Exception as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_health(root: str | Path | None = None) -> dict[str, Any]:
    """Collect a lightweight local git health snapshot."""

    repo_root = _base(root)
    code, branch_out, branch_err = _run_command(["git", "status", "--short", "--branch"], repo_root)
    if code != 0:
        return {
            "available": False,
            "branch": "",
            "ahead": 0,
            "behind": 0,
            "dirty": False,
            "changed": 0,
            "untracked": 0,
            "stashes": 0,
            "warnings": [branch_err or "git status failed"],
        }

    lines = branch_out.splitlines()
    branch_line = lines[0] if lines else ""
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    ahead = _parse_branch_counter(branch_line, "ahead")
    behind = _parse_branch_counter(branch_line, "behind")
    changed_lines = lines[1:]
    untracked = sum(1 for line in changed_lines if line.startswith("??"))
    changed = len(changed_lines)
    stash_code, stash_out, _ = _run_command(["git", "stash", "list"], repo_root)
    stashes = len([line for line in stash_out.splitlines() if line.strip()]) if stash_code == 0 else 0

    warnings: list[str] = []
    if changed:
        warnings.append(f"working tree has {changed} changed paths")
    if untracked:
        warnings.append(f"untracked paths={untracked}")
    if ahead:
        warnings.append(f"branch ahead={ahead}")
    if behind:
        warnings.append(f"branch behind={behind}")
    if stashes:
        warnings.append(f"stashes={stashes}")

    return {
        "available": True,
        "branch": branch,
        "ahead": ahead,
        "behind": behind,
        "dirty": changed > 0,
        "changed": changed,
        "untracked": untracked,
        "stashes": stashes,
        "warnings": warnings,
    }


def _parse_branch_counter(branch_line: str, label: str) -> int:
    marker = f"{label} "
    if marker not in branch_line:
        return 0
    tail = branch_line.split(marker, 1)[1]
    raw = tail.split(",", 1)[0].split("]", 1)[0].strip()
    try:
        return int(raw)
    except ValueError:
        return 0


def preflight_health(root: str | Path | None = None) -> dict[str, Any]:
    """Run local memory preflight in dry-run mode."""

    try:
        from src.memory.maintenance.pipeline_preflight import run_local_pipeline

        return run_local_pipeline(node="local", root=str(_base(root)), dry_run=True)
    except Exception as exc:
        return {
            "node": "local",
            "ok": False,
            "error": str(exc),
            "issues": [str(exc)],
            "snapshot": {},
        }


def _normalize_laptop_status(payload: Mapping[str, Any], source: str) -> dict[str, Any]:
    warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
    warnings.extend(_doctor_payload_warnings(payload))
    status = str(payload.get("status") or "").strip()
    if not status:
        status = "ok" if payload.get("ok") is True else "degraded" if payload.get("ok") is False else "unknown"
    available = bool(payload.get("available", status not in {"not_configured", "unknown", "error"}))
    normalized = dict(payload)
    normalized["checks"] = _compact_laptop_checks(payload.get("checks"))
    normalized.update(
        {
            "available": available,
            "status": status,
            "source": source,
            "warnings": warnings,
        }
    )
    return normalized


def _compact_laptop_checks(checks: Any, *, text_limit: int = 420) -> Any:
    if not isinstance(checks, list):
        return checks
    compacted: list[Any] = []
    for check in checks:
        if not isinstance(check, Mapping):
            compacted.append(check)
            continue
        row = dict(check)
        for field in ("stdout", "stderr"):
            if field in row:
                row[field] = _truncate_text(str(row.get(field) or ""), text_limit)
        compacted.append(row)
    return compacted


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [truncated {len(value) - limit} chars]"


def _doctor_payload_warnings(payload: Mapping[str, Any]) -> list[str]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return []
    warnings: list[str] = []
    for check in checks:
        if not isinstance(check, Mapping) or check.get("ok") is True:
            continue
        name = str(check.get("name") or "unknown")
        detail = str(check.get("detail") or "failed")
        hint = str(check.get("hint") or "").strip()
        warning = f"{name}: {detail}"
        if hint:
            warning = f"{warning} ({hint})"
        warnings.append(warning)
    return warnings


def laptop_remediation_commands(laptop: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return safe follow-up commands for laptop health failures."""

    failed = [
        item for item in laptop.get("failed_checks") or []
        if isinstance(item, Mapping)
    ]
    for check in laptop.get("checks") or []:
        if isinstance(check, Mapping) and check.get("ok") is not True:
            failed.append(check)

    commands: list[dict[str, str]] = []
    names = {str(item.get("name") or "") for item in failed}
    if "memory_audit" in names:
        commands.extend(
            [
                {
                    "kind": "diagnose",
                    "label": "Remote memory audit detail",
                    "command": (
                        "python ops\\remote\\kairos_remote.py kairos-python "
                        "--node laptop --command \"scripts/memory_audit.py --json\""
                    ),
                },
                {
                    "kind": "preview",
                    "label": "Remote memory repair plan",
                    "command": (
                        "python ops\\remote\\kairos_remote.py kairos-python "
                        "--node laptop --command \"scripts/memory_repair.py --json\""
                    ),
                },
                {
                    "kind": "manual_apply",
                    "label": "Remote repair apply, manual only",
                    "command": (
                        "python ops\\remote\\kairos_remote.py kairos-python "
                        "--node laptop --command \"scripts/memory_repair.py --apply --vectorize-missing --prune-stale --json\""
                    ),
                },
            ]
        )
    if not commands and str(laptop.get("status") or "") in {"degraded", "error", "unknown"}:
        commands.append(
            {
                "kind": "diagnose",
                "label": "Remote doctor detail",
                "command": "python ops\\remote\\kairos_remote.py doctor --node laptop --json",
            }
        )
    return commands


def _parse_laptop_command_payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["command_exit_code"] = result.returncode
    if result.returncode != 0 and result.stderr.strip():
        warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
        warnings.append(f"stderr: {result.stderr.strip()[:400]}")
        payload["warnings"] = warnings
    return payload


def laptop_health(
    root: str | Path | None = None,
    status_json: str | Path | None = None,
    command: str | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Collect laptop health from a configured JSON file or command."""

    configured_file = status_json or os.getenv("KAIROS_LAPTOP_STATUS_JSON", "")
    if configured_file:
        path = Path(configured_file)
        if not path.is_absolute():
            path = _base(root) / path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "available": False,
                "status": "error",
                "source": str(path),
                "warnings": [f"laptop status json failed: {exc}"],
            }
        if not isinstance(payload, Mapping):
            return {
                "available": False,
                "status": "error",
                "source": str(path),
                "warnings": ["laptop status json must contain an object"],
            }
        return _normalize_laptop_status(payload, str(path))

    configured_command = command or os.getenv("KAIROS_LAPTOP_STATUS_COMMAND", "")
    if configured_command:
        try:
            result = subprocess.run(
                configured_command,
                cwd=str(_base(root)),
                text=True,
                capture_output=True,
                timeout=timeout,
                shell=True,
            )
        except Exception as exc:
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": [f"laptop status command failed: {exc}"],
            }
        payload = _parse_laptop_command_payload(result)
        if payload is not None:
            return _normalize_laptop_status(payload, "command")
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or f"exit={result.returncode}"
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": [f"laptop status command failed: {stderr}"],
            }
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": [f"laptop status command returned invalid json: {exc}"],
            }
        if not isinstance(payload, Mapping):
            return {
                "available": False,
                "status": "error",
                "source": "command",
                "warnings": ["laptop status command must return a JSON object"],
            }
        return _normalize_laptop_status(payload, "command")

    return {
        "available": False,
        "status": "not_configured",
        "source": "",
        "warnings": ["laptop health is not configured in this local report"],
    }


def build_health(
    root: str | Path | None = None,
    include_preflight: bool = False,
    laptop_status_json: str | Path | None = None,
    laptop_status_command: str | None = None,
    laptop_status_timeout: int = 45,
) -> dict[str, Any]:
    """Build local operational health for the morning report."""

    health = {
        "git": git_health(root=root),
        "preflight": {},
        "laptop": laptop_health(
            root=root,
            status_json=laptop_status_json,
            command=laptop_status_command,
            timeout=laptop_status_timeout,
        ),
    }
    if include_preflight:
        health["preflight"] = preflight_health(root=root)
    return health
