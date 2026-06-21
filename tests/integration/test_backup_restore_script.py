from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name == "nt", reason="La integración usa utilidades POSIX reales")
def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    for command in ("bash", "git", "sqlite3"):
        if shutil.which(command) is None:
            pytest.skip(f"Falta {command}")

    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / "scripts" / "kairos-node.sh"
    target = scripts / "kairos-node.sh"
    shutil.copy2(source, target)
    target.chmod(0o755)
    (root / "memory").mkdir()
    database = root / "memory" / "sessions.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('original')")
    (root / "MEMORY.md").write_text("original\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@kairos.local"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Kairos Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    (fake_bin / "systemctl").write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> '{systemctl_log}'\n",
        encoding="utf-8",
    )
    (fake_bin / "curl").write_text(
        "#!/usr/bin/env bash\nprintf '{\"status\":\"ok\"}\\n'\n",
        encoding="utf-8",
    )
    for executable in fake_bin.iterdir():
        executable.chmod(0o755)

    backup_root = tmp_path / "backups"
    env = os.environ | {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "KAIROS_SERVICE_SCOPE": "user",
        "KAIROS_BACKUP_ROOT": str(backup_root),
        "KAIROS_MIN_FREE_KB": "0",
    }
    backup = subprocess.run(
        [str(target), "backup"], cwd=root, env=env, text=True, capture_output=True, check=True
    )
    backup_id = Path(backup.stdout.strip().split("backup=", 1)[1]).name

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE marker SET value='changed'")
    (root / "MEMORY.md").write_text("changed\n", encoding="utf-8")
    subprocess.run(
        [str(target), "restore", backup_id], cwd=root, env=env, text=True, capture_output=True, check=True
    )

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "original"
    assert (root / "MEMORY.md").read_text(encoding="utf-8") == "original\n"
    actions = systemctl_log.read_text(encoding="utf-8")
    assert "--user stop kairos" in actions
    assert "--user start kairos" in actions
