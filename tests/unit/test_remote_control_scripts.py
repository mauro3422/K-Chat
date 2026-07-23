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
LAN_FIELD_SMOKE = ROOT / "scripts" / "lan_field_smoke.py"
REMOTE_CLIENT = ROOT / "ops" / "remote" / "kairos_remote.py"
REMOTE_NODES_EXAMPLE = ROOT / "ops" / "remote" / "nodes.example.json"
PYTHON_BOOTSTRAP = ROOT / "scripts" / "_python_bootstrap.py"


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
    for action in ("Preflight", "MemoryPreflight", "Backup", "Pull", "Rollback", "Doctor", "LanDoctor", "ListNodes", "KairosPython", "Chat", "TaskCreate", "TaskList", "TaskShow", "TaskUpdate"):
        assert action in source
    for command in ("'preflight'", "'backup'", "'Restore'", "'rollback'"):
        assert command in source
    assert "ops\\remote\\kairos_remote.py" in source
    assert "$args=@('chat','--node',$Node,'--message',$Message)" in source
    assert "'lan-doctor'" in source
    assert "'preflight'" in source
    assert "'memory-preflight'" in source
    assert "'task-create'" in source
    assert "'task-update'" in source
    assert "'kairos-python'" in source
    assert "Invoke-RemoteClient $args" in source
    assert "--dry-run" in source


def test_remote_client_has_valid_python_syntax() -> None:
    source = REMOTE_CLIENT.read_text(encoding="utf-8")
    compile(source, str(REMOTE_CLIENT), "exec")
    assert "git pull --ff-only --autostash" in source
    assert "def action_doctor" in source
    assert "def action_lan_doctor" in source
    assert "lan-doctor" in source
    assert "memory-preflight" in source
    assert "preflight" in source
    assert "def action_chat" in source
    assert "def action_memory_preflight" in source
    assert "CODEX_DELEGATION_GUIDE" in source
    assert "task-create" in source
    assert "task-update" in source
    assert "kairos-python" in source
    assert "def remote_python_command" in source
    assert "fastembed=ok" in source
    assert "scripts/memory_audit.py" in source
    assert "venv/bin/python" in source
    assert "Kairos Python environment not found" in source
    assert "--raw-message" in source
    assert "--json" in source
    assert "--loopback" in source
    assert "--dry-run" in source
    assert "ConnectTimeout=8" in source


def test_lan_failover_drill_has_valid_python_syntax_and_guardrail() -> None:
    source = LAN_FAILOVER_DRILL.read_text(encoding="utf-8")
    compile(source, str(LAN_FAILOVER_DRILL), "exec")
    assert "--allow-service-control" in source
    assert "primary service emergency start" in source
    assert "temporary_primary_replay" in source


def test_lan_field_smoke_restores_memory_file_by_default() -> None:
    source = LAN_FIELD_SMOKE.read_text(encoding="utf-8")
    compile(source, str(LAN_FIELD_SMOKE), "exec")
    assert "restore_memory_file_snapshot" in source
    assert "--no-restore-memory-file" in source


def test_remote_nodes_example_shape() -> None:
    data = json.loads(REMOTE_NODES_EXAMPLE.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "linux" in data["nodes"]
    linux = data["nodes"]["linux"]
    for key in ("host", "user", "repo", "identityFile", "serviceUrl", "aliases", "expectedNodeId", "expectedRole"):
        assert key in linux
    assert "laptop" in linux["aliases"]
    assert linux["expectedRole"] == "secondary"


def test_remote_client_resolves_explicit_aliases_but_not_unknown_single_profile(monkeypatch) -> None:
    module = load_remote_client_module()
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.40",
        user="maurol",
        repo="/home/maurol/dev/K-Chat",
        identity_file=__file__,
        aliases=("laptop", "secondary"),
    )
    profiles = {
        "linux": profile,
        "laptop": profile,
        "secondary": profile,
    }

    assert module.require_profile(profiles, "laptop") is profile
    with pytest.raises(SystemExit) as exc:
        module.require_profile(profiles, "primary")

    assert "Unknown node 'primary'" in str(exc.value)


def test_remote_client_rediscoveres_moved_ipv4_node_by_expected_identity(monkeypatch, tmp_path) -> None:
    module = load_remote_client_module()
    identity = tmp_path / "id_ed25519"
    identity.write_text("fake", encoding="utf-8")
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.38",
        user="maurol",
        repo="/home/maurol/dev/K-Chat",
        identity_file=str(identity),
        service_url="http://192.168.1.38:8000",
        expected_node_id="pc-secundaria",
    )

    monkeypatch.setattr(
        module,
        "_host_node_state",
        lambda _profile, host, *, timeout: {"node_id": "pc-secundaria"} if host == "192.168.1.39" else None,
    )

    resolved = module.discover_profile_host(profile, workers=8)

    assert resolved.host == "192.168.1.39"
    assert resolved.service_url == "http://192.168.1.39:8000"
    assert profile.host == "192.168.1.38"


def test_remote_client_does_not_rediscover_without_an_expected_identity(monkeypatch, tmp_path) -> None:
    module = load_remote_client_module()
    identity = tmp_path / "id_ed25519"
    identity.write_text("fake", encoding="utf-8")
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.38",
        user="maurol",
        repo="/home/maurol/dev/K-Chat",
        identity_file=str(identity),
    )

    monkeypatch.setattr(module, "_host_node_state", lambda *_args, **_kwargs: pytest.fail("must not scan without identity"))

    assert module.discover_profile_host(profile) is profile


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
        lambda _profile, *, primary_url, secondary_url, loopback=False: [
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


def test_lan_doctor_loopback_emits_mode_and_uses_primary_as_secondary(monkeypatch, capsys, tmp_path) -> None:
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
        lambda _profile, *, primary_url, secondary_url, loopback=False: [
            module.DoctorCheck(name="lan_smoke", ok=loopback, detail=f"{primary_url} {secondary_url}"),
        ],
    )

    assert module.action_lan_doctor(
        profile,
        primary_url="http://primary:8000",
        secondary_url="",
        json_output=True,
        loopback=True,
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "loopback"
    assert payload["secondary_url"] == "http://primary:8000"
    assert payload["checks"][0]["ok"] is True


def test_smoke_check_passes_loopback_flag(monkeypatch) -> None:
    module = load_remote_client_module()
    captured = {}

    def fake_run(command, cwd, text, capture_output, timeout):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    check = module._smoke_check("http://primary:8000", "", loopback=True)

    assert check.ok is True
    assert "--loopback" in captured["command"]
    assert "--secondary-url" not in captured["command"]


def test_preflight_loopback_does_not_require_remote_profile(monkeypatch, tmp_path) -> None:
    module = load_remote_client_module()
    missing_config = tmp_path / "missing-remote-nodes.json"
    captured = {}

    def fake_action(profile, *, primary_url, secondary_url, json_output=False, loopback=False):
        captured["profile"] = profile
        captured["primary_url"] = primary_url
        captured["secondary_url"] = secondary_url
        captured["loopback"] = loopback
        return 0

    monkeypatch.setattr(module, "action_lan_doctor", fake_action)

    assert module.main([
        "preflight",
        "--loopback",
        "--config",
        str(missing_config),
        "--primary-url",
        "http://primary:8000",
    ]) == 0

    assert captured["profile"].name == "linux"
    assert captured["primary_url"] == "http://primary:8000"
    assert captured["secondary_url"] == ""
    assert captured["loopback"] is True


def test_remote_node_state_detects_profile_identity_mismatch(monkeypatch, tmp_path) -> None:
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
        expected_node_id="pc-secundaria",
        expected_role="secondary",
    )

    monkeypatch.setattr(
        module,
        "_http_json",
        lambda _profile, _path, timeout=8: {
            "node_id": "pc-principal",
            "role": "primary",
            "healthy": True,
        },
    )

    check = module._http_check(profile, "node_state", "/api/node/state")

    assert check.ok is False
    assert "expected node_id=pc-secundaria" in check.detail
    assert "expected role=secondary" in check.detail


def test_remote_node_state_accepts_temporary_promotion_for_expected_preferred_role(monkeypatch, tmp_path) -> None:
    module = load_remote_client_module()
    identity = tmp_path / "id_ed25519"
    identity.write_text("fake", encoding="utf-8")
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.40",
        user="maurol",
        repo="/home/maurol/dev/K-Chat",
        identity_file=str(identity),
        expected_role="secondary",
    )

    monkeypatch.setattr(
        module,
        "_http_json",
        lambda _profile, _path, timeout=8: {
            "node_id": "pc-secundaria",
            "role": "primary",
            "preferred_role": "secondary",
            "healthy": True,
        },
    )

    check = module._http_check(profile, "node_state", "/api/node/state")

    assert check.ok is True


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


def test_remote_doctor_uses_liveness_endpoint(monkeypatch, tmp_path) -> None:
    module = load_remote_client_module()
    identity = tmp_path / "id_ed25519"
    identity.write_text("fake", encoding="utf-8")
    profile = module.NodeProfile(
        name="linux",
        host="192.168.1.40",
        user="maurol",
        repo=str(tmp_path),
        identity_file=str(identity),
        service_url="http://192.168.1.40:8000",
    )
    paths = []

    monkeypatch.setattr(module.Path, "exists", lambda _path: True)
    monkeypatch.setattr(module, "_ssh_check", lambda *_args, **_kwargs: module.DoctorCheck(name=_args[1], ok=True, detail="ok"))

    def fake_http_check(_profile, name, path, *, timeout=8):
        paths.append((name, path))
        return module.DoctorCheck(name=name, ok=True, detail="ok")

    monkeypatch.setattr(module, "_http_check", fake_http_check)

    checks = module.collect_doctor_checks(profile)

    assert [check.name for check in checks if check.name == "health"] == ["health"]
    assert ("health", "/live") in paths
    assert ("health", "/health") not in paths


def test_memory_preflight_action_emits_json(monkeypatch, capsys, tmp_path) -> None:
    module = load_remote_client_module()
    from scripts import memory_pipeline_preflight as pipeline

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
        pipeline,
        "run_local_pipeline",
        lambda *, node, dry_run=False: {"node": node, "ok": True, "snapshot": {"vectors": 1}},
    )
    monkeypatch.setattr(
        pipeline,
        "run_remote_pipeline",
        lambda *, node, runner, dry_run=False: {"node": node, "ok": False, "snapshot": {}, "issues": ["remote failed"]},
    )

    assert module.action_memory_preflight(profile, json_output=True) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["failed_nodes"] == ["linux"]


def test_remote_doctor_hint_names_common_lan_failures() -> None:
    module = load_remote_client_module()

    assert "SSH no autentica" in module.doctor_hint("ssh", stderr="Permission denied (publickey)")
    assert "KAIROS_PEER_URLS" in module.doctor_hint("sync_status")
    assert "puerto SSH" in module.doctor_hint("ssh", detail="connection refused")
    assert "Auditoria de memoria" in module.doctor_hint("memory_audit")


def test_memory_script_bootstrap_reports_missing_repo_env(monkeypatch, tmp_path) -> None:
    spec = importlib.util.spec_from_file_location("kairos_python_bootstrap_test", PYTHON_BOOTSTRAP)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    root = tmp_path / "Kairos"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (root / "src").mkdir()
    (root / "requirements.txt").write_text("fastembed\nsqlite-vec\n", encoding="utf-8")
    script = scripts / "memory_audit.py"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _module: None)

    with pytest.raises(SystemExit) as exc:
        module.ensure_repo_python(str(script), command_name="scripts/memory_audit.py")

    message = str(exc.value)
    assert "Kairos Python environment not found." in message
    assert "Expected a repo venv or the current Python with required packages." in message
    if module.os.name == "nt":
        assert "py -3 -m venv .venv" in message
        assert ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt" in message
    else:
        assert "python3 -m venv .venv" in message
        assert ".venv/bin/python -m pip install -r requirements.txt" in message


def test_remote_python_bootstrap_does_not_fallback_to_global_python() -> None:
    module = load_remote_client_module()

    bootstrap = module.remote_python_bootstrap()

    assert "venv/bin/python" in bootstrap
    assert ".venv/bin/python" in bootstrap
    assert "Kairos Python environment not found" in bootstrap
    assert 'python3 -c "import fastembed, sqlite_vec"' in bootstrap


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
    assert 'EXEC_START="$ROOT/venv/bin/python -m uvicorn"' in source
    assert source.index('"$ROOT/venv/bin/python"') < source.index('"$ROOT/.venv/bin/python"')
    assert 'systemctl --user stop "$WATCHDOG_SERVICE"' in source
    assert 'install -m 600 "$ROOT/.kairos/k-chat-watchdog.service"' in source
    assert source.index('systemctl --user restart "$SERVICE"') < source.index(
        'systemctl --user restart "$WATCHDOG_SERVICE"'
    )


def test_linux_bootstrap_prefers_repo_venv_python() -> None:
    source = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    assert 'PYTHON="$ROOT/venv/bin/python"' in source
    assert 'PYTHON="$ROOT/.venv/bin/python"' in source
    assert 'PYTHON="$(command -v python3)"' in source
    assert source.index('PYTHON="$ROOT/venv/bin/python"') < source.index('PYTHON="$ROOT/.venv/bin/python"')
