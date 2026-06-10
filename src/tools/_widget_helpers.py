_saved_widget_repo = None


def get_saved_widget_repo():
    global _saved_widget_repo
    if _saved_widget_repo is None:
        from src.memory.repos import SavedWidgetRepository
        _saved_widget_repo = SavedWidgetRepository()
    return _saved_widget_repo


def sanitize_widget_id(widget_id: str) -> str:
    return "".join(c for c in widget_id if c.isalnum() or c in ("-", "_")).lower().strip()


def validate_widget_args(session_id: str | None, widget_id: str) -> tuple[str, str] | str:
    if not session_id:
        return "[ERROR] session_id was not specified in the tool execution."
    clean_id = sanitize_widget_id(widget_id)
    if not clean_id:
        return "[ERROR] Invalid widget identifier."
    return session_id, clean_id
