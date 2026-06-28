from __future__ import annotations

import shutil
import subprocess
import json
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LINUX_SCRIPT = ROOT / "scripts" / "kairos-node.sh"
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "bootstrap-linux-remote-control.sh"
LINUX_SERVICE_SCRIPT = ROOT / "scripts" / "install-linux-user-service.sh"
WINDOWS_SCRIPT = ROOT / "scripts" / "remote-kairos.ps1"
WINDOWS_SERVICE_SCRIPT = ROOT / "scripts" / "kairos-windows-service.ps1"
WINDOWS_RUNNER = ROOT / "scripts" / "run_windows_service.py"
LAN_FAILOVER_DRILL = ROOT / "scripts" / "lan_failover_drill.py"
REMOTE_CLIENT = ROOT / "ops" / "remote" / "kairos_remote.py"
REMOTE_NODES_EXAMPLE = ROOT / "ops" / "remote" / "nodes.example.json"


def load_remote_client_module():
    spec = importlib.util.spec_from_file_location("kairos_remote_test", REMOTE_CLIENT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_linux_control_scripts_have_valid_bash_syntax() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    for script in (LINUX_SCRIPT, BOOTSTRAP_SCRIPT, LINUX_SERVICE_SCRIPT):
        source = script.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        result = subprocess.run(
            [bash, "-n"],
            input=source,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_linux_control_exposes_recovery_contract() -> None:
    source = LINUX_SCRIPT.read_text(encoding="utf-8")
    for function in ("preflight()", "backup()", "restore_backup()", "rollback_to()", "update()"):
        assert function in source
    assert "sqlite3 \"$source\" \".backup '$target'\"" in source
    assert 'for database_root in "$ROOT/data" "$ROOT/memory"' in source
    assert 'chmod 600 "$target"' in source
    assert 'install -d -m 700 "$BACKUP_ROOT" "$destination"' in source
    assert 'rollback_to "$previous_commit"' in source
    assert 'KAIROS_BACKUP_KEEP:-7' in source
    assert 'while [[ -e "$destination" ]]' in source
    assert "preflight) preflight" in source
    assert "backup) backup" in source
    assert 'restore) restore_backup "${2:-}"' in source


def test_restore_validates_backup_before_stopping_service() -> None:
    source = LINUX_SCRIPT.read_text(encoding="utf-8")
    body = source.split("restore_backup()", 1)[1].split("rollback_to()", 1)[0]
    assert body.index("PRAGMA integrity_check") < body.index("service_control stop")
    assert body.index("backup") < body.index("service_control stop")
    assert '[[ "$relative" == data/* || "$relative" == memory/* ]]' in body
    assert 'rollback) rollback_to "${2:-}"' in source


def test_update_orders_preflight_backup_and_previous_commit() -> None:
    source = LINUX_SCRIPT.read_text(encoding="utf-8")
    update_body = source[source.index("update() {") : source.index('\ncase "$ACTION"')]
    assert update_body.index("preflight") < update_body.index("backup")
    assert update_body.index("backup") < update_body.index('previous_commit="$(git rev-parse HEAD)"')
    assert "npm ci &&" in update_body
    assert "npm run build &&" in update_body
    assert "service_control restart &&" in update_body
    assert update_body.index("git pull --ff-only") < update_body.index("npm run build")


def test_windows_remote_control_maps_recovery_actions() -> None:
    source = WINDOWS_SCRIPT.read_text(encoding="utf-8")
    for action in ("Preflight", "Backup", "Pull", "Rollback", "Doctor", "LanDoctor", "ListNodes", "Chat", "TaskCreate", "TaskList", "TaskShow", "TaskUpdate"):
        assert action in source
    for command in ("'preflight'", "'backup'", "'Restore'", "'rollback'"):
        assert command in source
    assert "ops\\remote\\kairos_remote.py" in source
    assert "$args=@('chat','--node',$Node,'--message',$Message)" in source
    assert "'lan-doctor'" in source
    assert "'task-create'" in source
    assert "'task-update'" in source
    assert "Invoke-RemoteClient $args" in source


def test_remote_client_has_valid_python_syntax() -> None:
    source = REMOTE_CLIENT.read_text(encoding="utf-8")
    compile(source, str(REMOTE_CLIENT), "exec")
    assert "git pull --ff-only --autostash" in source
    assert "def action_doctor" in source
    assert "def action_lan_doctor" in source
    assert "lan-doctor" in source
    assert "def action_chat" in source
    assert "CODEX_DELEGATION_GUIDE" in source
    assert "task-create" in source
    assert "task-update" in source
    assert "--raw-message" in source
    assert "--json" in source
    assert "ConnectTimeout=8" in source


def test_lan_failover_drill_has_valid_python_syntax_and_guardrail() -> None:
    source = LAN_FAILOVER_DRILL.read_text(encoding="utf-8")
    compile(source, str(LAN_FAILOVER_DRILL), "exec")
    assert "--allow-service-control" in source
    assert "primary service emergency start" in source
    assert "temporary_primary_replay" in source


def test_remote_nodes_example_shape() -> None:
    data = json.loads(REMOTE_NODES_EXAMPLE.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "linux" in data["nodes"]
    linux = data["nodes"]["linux"]
    for key in ("host", "user", "repo", "identityFile", "serviceUrl"):
        assert key in linux


def test_lan_doctor_report_can_emit_json(monkeypatch, capsys, tmp_path) -> None:
    module = load_remote_client_module()
    identity = tmp_path / "id_ed25519"
    identity.write_text("fake", encoding="utf-8")
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.40",
        user="maurol",
        repo="/home/maurol/dev/K-Chat",
        identity_file=str(identity),
        service_url="http://192.168.1.40:8000",
    )

    monkeypatch.setattr(
        module,
        "collect_lan_doctor_checks",
        lambda _profile, *, primary_url, secondary_url: [
            module.DoctorCheck(name="local_health", ok=True, detail=primary_url),
            module.DoctorCheck(name="lan_smoke", ok=False, detail=secondary_url, hint="revisar smoke"),
        ],
    )

    assert module.action_lan_doctor(
        profile,
        primary_url="http://primary:8000",
        secondary_url="http://secondary:8000",
        json_output=True,
    ) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["primary_url"] == "http://primary:8000"
    assert payload["secondary_url"] == "http://secondary:8000"
    assert payload["checks"][1]["hint"] == "revisar smoke"


def test_remote_chat_wraps_codex_delegation_by_default() -> None:
    module = load_remote_client_module()

    wrapped = module.delegated_message("diagnostica health")

    assert "Codex esta hablando con Kairos" in wrapped
    assert wrapped.endswith("diagnostica health")
    assert module.delegated_message("diagnostica health", raw_message=True) == "diagnostica health"


def test_remote_doctor_report_can_emit_json(monkeypatch, capsys, tmp_path) -> None:
    module = load_remote_client_module()
    identity = tmp_path / "id_ed25519"
    identity.write_text("fake", encoding="utf-8")
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.40",
        user="maurol",
        repo="/home/maurol/dev/K-Chat",
        identity_file=str(identity),
        service_url="http://192.168.1.40:8000",
    )

    monkeypatch.setattr(
        module,
        "collect_doctor_checks",
        lambda _profile: [
            module.DoctorCheck(name="profile", ok=True, detail="ok"),
            module.DoctorCheck(name="health", ok=False, detail="degraded", hint="revisar health"),
        ],
    )

    assert module.action_doctor(profile, json_output=True) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["passed"] == 1
    assert payload["total"] == 2
    assert payload["checks"][1]["hint"] == "revisar health"


def test_remote_doctor_hint_names_common_lan_failures() -> None:
    module = load_remote_client_module()

    assert "SSH no autentica" in module.doctor_hint("ssh", stderr="Permission denied (publickey)")
    assert "KAIROS_PEER_URLS" in module.doctor_hint("sync_status")
    assert "puerto SSH" in module.doctor_hint("ssh", detail="connection refused")


def test_windows_control_has_valid_powershell_syntax() -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")
    for script in (WINDOWS_SCRIPT, WINDOWS_SERVICE_SCRIPT):
        escaped = str(script).replace("'", "''")
        command = (
            "$errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$null, [ref]$errors) > $null; "
            "if ($errors.Count) { $errors | Out-String | Write-Error; exit 1 }"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", command],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_windows_service_is_persistent_and_has_bounded_shutdown() -> None:
    source = WINDOWS_SERVICE_SCRIPT.read_text(encoding="utf-8")
    assert "New-ScheduledTaskTrigger -AtLogOn" in source
    assert "Register-ScheduledTask" in source
    assert "-RestartCount 5" in source
    assert "Kairos Discovery LAN" in source
    assert "run_windows_service.py" in source
    assert "Enable-ScheduledTask" in source

    runner = WINDOWS_RUNNER.read_text(encoding="utf-8")
    assert "timeout_graceful_shutdown=8" in runner
    assert "access_log=False" in runner
    assert "class RotatingTextStream" in runner
    compile(runner, str(WINDOWS_RUNNER), "exec")


def test_windows_service_repo_default_is_resolved_after_param_binding() -> None:
    source = WINDOWS_SERVICE_SCRIPT.read_text(encoding="utf-8")
    param_block = source.split("param(", 1)[1].split("\n)\n", 1)[0]

    assert "[string]$Repo = ''" in param_block
    assert "if(-not $Repo)" in source
    assert "$MyInvocation.MyCommand.Path" in source
    assert "[string]$Repo = (Split-Path -Parent $PSScriptRoot)" not in source


def test_linux_bootstrap_firewall_does_not_assume_one_subnet() -> None:
    source = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    assert "10.0.0.0/8 172.16.0.0/12 192.168.0.0/16" in source
    assert 'port 42429 proto udp' in source


def test_linux_user_service_has_restart_and_bounded_shutdown() -> None:
    source = LINUX_SERVICE_SCRIPT.read_text(encoding="utf-8")
    assert "--timeout-graceful-shutdown 8" in source
    assert "TimeoutStopSec=12" in source
    assert 'systemctl --user enable --now "$SERVICE"' in source
    assert 'UNIT_FILE="$UNIT_DIR/${SERVICE}.service"' in source
    assert 'UNIT_FILE="$ROOT/.kairos/${SERVICE}.service"' not in source
    assert 'if [[ -L "$UNIT_FILE" ]]' in source
