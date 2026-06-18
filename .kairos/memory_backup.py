#!/usr/bin/env python3
"""Backup emergency de memoria: MEMORY.md + memory.db.
Crea snapshots con timestamp en backups/ dentro del proyecto.

Uso:
    python3 .kairos/memory_backup.py             # backup completo
    python3 .kairos/memory_backup.py --list       # listar backups existentes
    python3 .kairos/memory_backup.py --restore N  # restaurar backup #N
"""

import asyncio
import json
import logging
import sys
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_ROOT / "backups" / "memory"
MEMORY_MD = PROJECT_ROOT / "MEMORY.md"
MEMORY_DB = PROJECT_ROOT / "data" / "kairos_memory.db"
SESSIONS_DB = PROJECT_ROOT / "data" / "kairos_sessions.db"
MAX_BACKUPS = 20

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def do_backup() -> str:
    """Crea un snapshot timestamped de MEMORY.md + memory.db + sesiones."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"backup_{ts}"
    backup_path.mkdir(exist_ok=True)

    # MEMORY.md (source of truth)
    if MEMORY_MD.exists():
        shutil.copy2(MEMORY_MD, backup_path / "MEMORY.md")
    
    # memory.db (embeddings + índices)
    if MEMORY_DB.exists():
        shutil.copy2(MEMORY_DB, backup_path / "kairos_memory.db")
    
    # sessions.db (chats)
    if SESSIONS_DB.exists():
        shutil.copy2(SESSIONS_DB, backup_path / "kairos_sessions.db")

    # Export JSON de memory.db entries
    try:
        from src.memory.memory_db_path import resolve_memory_db_path
        import sqlite3
        conn = sqlite3.connect(resolve_memory_db_path())
        rows = conn.execute("SELECT key, value FROM memory_index").fetchall()
        conn.close()
        with open(backup_path / "entries.json", "w") as f:
            json.dump([{"key": k, "value": v} for k, v in rows], f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"⚠️  Export JSON falló: {e}")

    # Rotar backups viejos
    all_backups = sorted(BACKUP_DIR.iterdir(), key=lambda p: p.name)
    while len(all_backups) > MAX_BACKUPS:
        shutil.rmtree(all_backups[0], ignore_errors=True)
        all_backups = all_backups[1:]

    size = sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file())
    log.info(f"✅ Backup creado: backup_{ts} ({size / 1024:.0f} KB)")
    return str(backup_path)


def list_backups() -> list[dict]:
    """Lista backups existentes con metadata."""
    if not BACKUP_DIR.exists():
        return []
    backups = []
    for p in sorted(BACKUP_DIR.iterdir(), key=lambda p: p.name):
        if not p.is_dir():
            continue
        files = {f.name: f.stat().st_size for f in p.rglob("*") if f.is_file()}
        backups.append({
            "name": p.name,
            "path": str(p),
            "files": files,
            "total_kb": sum(files.values()) / 1024,
        })
    return backups


def restore_backup(n: int) -> None:
    """Restaura backup #N (1-indexed)."""
    all_backups = list_backups()
    if not all_backups:
        log.error("❌ No hay backups para restaurar.")
        return
    if n < 1 or n > len(all_backups):
        log.error(f"❌ Backup #{n} no existe. Hay {len(all_backups)} backups.")
        return

    backup = all_backups[n - 1]
    src = Path(backup["path"])
    
    # Restaurar MEMORY.md
    if (src / "MEMORY.md").exists():
        shutil.copy2(src / "MEMORY.md", MEMORY_MD)
        log.info("✅ MEMORY.md restaurado")
    
    # Restaurar memory.db
    if (src / "kairos_memory.db").exists():
        MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "kairos_memory.db", MEMORY_DB)
        log.info("✅ kairos_memory.db restaurado")
    
    # Restaurar sessions.db
    if (src / "kairos_sessions.db").exists():
        SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "kairos_sessions.db", SESSIONS_DB)
        log.info("✅ kairos_sessions.db restaurado")


async def do_curate():
    """Ejecuta el curador de memoria."""
    try:
        from src.memory.curator.curate import curate_all as curator
        from src.tools.save_memory import run as save_memory_run
        log.info("🧠 Curando memoria...")
        r = await curator(save_memory_fn=lambda k, v: save_memory_run(key=k, value=v))
        if r["saved"]:
            log.info(f"✅ {r['saved']} nuevas entradas guardadas en MEMORY.md")
        else:
            log.info("ℹ️  No hay info nueva para curar.")
        return r
    except Exception as e:
        log.error(f"❌ Curador falló: {e}")
        raise


async def async_main():
    action = sys.argv[1] if len(sys.argv) > 1 else "backup"
    
    if action == "--list":
        backups = list_backups()
        if not backups:
            print("📭 No hay backups.")
            return
        print(f"📦 {len(backups)} backups:")
        for i, b in enumerate(backups, 1):
            files_str = ", ".join(f"{n}={s/1024:.0f}KB" for n, s in b["files"].items())
            print(f"  [{i}] {b['name']} — {files_str}")

    elif action == "--restore":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        restore_backup(n)
        print("✅ Restauración completa. Corré 'manage_memory sync' si es necesario.")

    elif action == "--curate":
        r = await do_curate()
        for e in r["entries"]:
            print(f"  [{e['key']}] {e['value'][:80]}")

    elif action in ("backup", "--backup"):
        do_backup()

    else:
        print(f"Uso: python3 {sys.argv[0]} [backup|--list|--restore N|--curate]")
        print(f"  backup      → crear snapshot (default)")
        print(f"  --list      → listar backups")
        print(f"  --restore N → restaurar backup #N")
        print(f"  --curate    → ejecutar curador LLM")


if __name__ == "__main__":
    asyncio.run(async_main())
