import logging

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "save_widget",
        "description": "Saves or promotes an interactive widget to 'official' status in the session database so it persists, is versioned, and can be iterated on.",
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {
                    "type": "string",
                    "description": "The identifier or unique key of the widget (e.g. 'calculator', 'blog', 'notes')."
                },
                "code": {
                    "type": "string",
                    "description": "The complete self-contained HTML, CSS, and JavaScript code of the widget."
                },
                "description": {
                    "type": "string",
                    "description": "Short description of the change or the initial widget version."
                }
            },
            "required": ["widget_id", "code"]
        }
    }
}


def run(*args, **kwargs) -> str:
    widget_id = args[0] if args else kwargs.get("widget_id") or kwargs.get("key", "")
    code = args[1] if len(args) > 1 else kwargs.get("code", "")
    description = args[2] if len(args) > 2 else kwargs.get("description", "")
    _session_id = kwargs.get("_session_id")
    if len(args) > 3 and _session_id is None:
        _session_id = args[3]
    from src.tools._widget_helpers import validate_widget_args, get_saved_widget_repo
    result = validate_widget_args(_session_id, widget_id)
    if isinstance(result, str):
        return result
    _session_id, clean_id = result

    try:
        res = get_saved_widget_repo().save(_session_id, clean_id, code, description)
        return f"[OK] Widget '{clean_id}' saved correctly as Version {res['version']}."
    except Exception as e:
        logger.error("Error guardando widget %s para session %s: %s", clean_id, _session_id, e)
        return "[ERROR] Could not save the widget."
