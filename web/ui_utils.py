from typing import Any


def _ensure_dict(row: Any) -> dict[str, Any]:
    """Convierte sqlite3.Row a dict si es necesario."""
    if hasattr(row, 'keys'):
        return dict(row)
    return row
