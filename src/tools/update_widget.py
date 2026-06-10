import logging

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "update_widget",
        "description": "Updates the code of an existing official widget, saving it as a new version in the session database so it can be iterated on without losing its previous state.",
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {
                    "type": "string",
                    "description": "The identifier or unique key of the widget to update (e.g. 'calculator', 'blog')."
                },
                "code": {
                    "type": "string",
                    "description": "The new complete self-contained HTML, CSS, and JavaScript code for the widget."
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the changes made in this version (e.g. 'Added back button', 'Bug fixes')."
                }
            },
            "required": ["widget_id", "code"]
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


def run(widget_id: str, code: str, description: str = "", _session_id: str | None = None) -> str:
    from src.tools._widget_helpers import validate_widget_args
    result = validate_widget_args(_session_id, widget_id)
    if isinstance(result, str):
        return result
    _session_id, clean_id = result

    try:
        existing = _get_saved_widget_repo().get(_session_id, clean_id)
        if not existing:
            return f"[ERROR] The widget '{clean_id}' does not exist as an official widget in this session. Use 'save_widget' first to consolidate it."

        res = _get_saved_widget_repo().save(_session_id, clean_id, code, description)
        return f"[OK] Widget '{clean_id}' updated correctly to Version {res['version']}."
    except Exception as e:
        logger.error("Error actualizando widget %s para session %s: %s", clean_id, _session_id, e)
        return "[ERROR] Could not update the widget."
