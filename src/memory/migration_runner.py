from typing import Any, Callable, Sequence


Migration = Callable[[Any, Any], None]


def run_pending_migrations(
    conn: Any,
    engine: Any,
    migrations: Sequence[Migration],
    current_version: int,
    schema_table: str = "schema_version",
) -> None:
    cursor = conn.cursor()
    for version, migration in enumerate(migrations[current_version:], start=current_version + 1):
        migration(conn, engine)
        cursor.execute(f"DELETE FROM {schema_table}")
        cursor.execute(
            f"INSERT INTO {schema_table} (version) VALUES (?)",
            (version,),
        )
        engine.commit(conn)
