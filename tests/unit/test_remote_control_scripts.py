from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LINUX_SCRIPT = ROOT / "scripts" / "kairos-node.sh"
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "bootstrap-linux-remote-control.sh"
WINDOWS_SCRIPT = ROOT / "scripts" / "remote-kairos.ps1"


def test_linux_control_scripts_have_valid_bash_syntax() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    for script in (LINUX_SCRIPT, BOOTSTRAP_SCRIPT):
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
    assert update_body.index("git pull --ff-only") < update_body.index("npm run build")


def test_windows_remote_control_maps_recovery_actions() -> None:
    source = WINDOWS_SCRIPT.read_text(encoding="utf-8")
    for action in ("Preflight", "Backup", "Rollback"):
        assert action in source
    for command in ("'preflight'", "'backup'", "'restore'", "'rollback'"):
        assert command in source


def test_windows_control_has_valid_powershell_syntax() -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not available")
    escaped = str(WINDOWS_SCRIPT).replace("'", "''")
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
