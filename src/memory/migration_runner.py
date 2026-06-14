from typing import Any, Callable, Sequence


Migration = Callable[[Any, Any], None]


async def run_pending_migrations(
    conn: Any,
    engine: Any,
    migrations: Sequence[Migration],
    current_version: int,
    schema_table: str = "schema_version",
) -> None:
    cursor = await conn.cursor()
    for version, migration in enumerate(migrations[current_version:], start=current_version + 1):
        await migration(conn, engine)
        await cursor.execute(f"DELETE FROM {schema_table}")
        await cursor.execute(
            f"INSERT INTO {schema_table} (version) VALUES (?)",
            (version,),
        )
        await engine.commit(conn)
