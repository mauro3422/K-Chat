"""Backfill content_hash for existing vec_meta entries."""
import hashlib
import re
import sqlite3

DB_PATH = "data/kairos_memory.db"


def normalize(text: str) -> str:
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`[^`]+`', '', text)
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT rowid, text FROM vec_meta WHERE content_hash IS NULL OR content_hash = ''"
    ).fetchall()

    updated = 0
    for rowid, text in rows:
        if not text:
            continue
        h = hashlib.md5(normalize(text[:4000]).encode()).hexdigest()
        conn.execute("UPDATE vec_meta SET content_hash = ? WHERE rowid = ?", (h, rowid))
        updated += 1

    conn.commit()
    conn.close()
    print(f"Backfilled {updated} content_hashes")


if __name__ == "__main__":
    main()
