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


async def run(*args, **kwargs) -> str:
    widget_id = args[0] if args else kwargs.get("widget_id") or kwargs.get("key", "")
    _session_id = kwargs.get("_session_id")
    _repos = kwargs.get("_repos")
    if len(args) > 1 and _session_id is None:
        _session_id = args[1]
    from src.tools._widget_helpers import validate_widget_args, get_saved_widget_repo
    result = validate_widget_args(_session_id, widget_id)
    if isinstance(result, str):
        return result
    _session_id, clean_id = result

    repo = get_saved_widget_repo(repo=_repos.saved_widgets if _repos else None)

    try:
        widget = await repo.get(clean_id)
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
