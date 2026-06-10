import logging

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_widget_code",
        "description": "Retrieves the current source code and version of a previously saved official widget so it can be analyzed and improved.",
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {
                    "type": "string",
                    "description": "The identifier or unique key of the widget to retrieve (e.g. 'calculator', 'blog')."
                }
            },
            "required": ["widget_id"]
        }
    }
}


_saved_widget_repo = None


def _get_saved_widget_repo():
    global _saved_widget_repo
    if _saved_widget_repo is None:
        from src.memory.repositories import SavedWidgetRepository
        _saved_widget_repo = SavedWidgetRepository()
    return _saved_widget_repo


def run(widget_id: str, _session_id: str | None = None) -> str:
    from src.tools._widget_helpers import validate_widget_args
    result = validate_widget_args(_session_id, widget_id)
    if isinstance(result, str):
        return result
    _session_id, clean_id = result

    try:
        widget = _get_saved_widget_repo().get(_session_id, clean_id)
        if not widget:
            return f"[ERROR] The widget '{clean_id}' does not exist or has not been officially saved in this session."
        
        return (
            f"Widget: {widget['widget_id']}\n"
            f"Active Version: {widget['version']}\n"
            f"Description: {widget['description']}\n"
            f"Last Modified: {widget['updated_at']}\n"
            f"--- SOURCE CODE ---\n"
            f"{widget['code']}\n"
        )
    except Exception as e:
        logger.error("Error retrieving widget %s for session %s: %s", clean_id, _session_id, e)
        return "[ERROR] Could not retrieve the widget code."
