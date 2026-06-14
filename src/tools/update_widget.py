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


async def run(*args, **kwargs) -> str:
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
        existing = await get_saved_widget_repo().get(clean_id)
        if not existing:
            return f"[ERROR] The widget '{clean_id}' does not exist as an official widget in this session. Use 'save_widget' first to consolidate it."

        res = await get_saved_widget_repo().save(_session_id, clean_id, code, description)
        return f"[OK] Widget '{clean_id}' updated correctly to Version {res['version']}."
    except Exception as e:
        logger.error("Error actualizando widget %s para session %s: %s", clean_id, _session_id, e)
        return "[ERROR] Could not update the widget."
