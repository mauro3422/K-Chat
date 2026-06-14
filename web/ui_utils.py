from typing import Any


def _ensure_dict(row: Any) -> dict[str, Any]:
    """Convierte sqlite3.Row o SimpleNamespace a dict si es necesario."""
    if hasattr(row, 'keys'):
        return dict(row)
    if hasattr(row, '__dict__'):
        return vars(row)
    return row
