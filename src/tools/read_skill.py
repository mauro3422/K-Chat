import logging

logger = logging.getLogger(__name__)

DEFINITION = {
    "type": "function",
    "function": {
        "name": "read_skill",
        "description": "Looks up the detailed instructions of a skill (such as 'html-widgets') when you need to perform a specialized task or program visual interfaces.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the skill to look up (e.g. 'html-widgets')."
                }
            },
            "required": ["name"]
        }
    }
}


async def run(name=None, **kwargs) -> str:
    if name is None:
        name = kwargs.get("name", kwargs.get("skill", kwargs.get("skill_name", "")))
    _session_id = kwargs.get("_session_id")
    _skill_registry = kwargs.get("_skill_registry")
    """Reads and returns the content of a skill from the skills/ folder."""
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
    if not safe_name:
        return "[ERROR] Invalid skill name."

    if _skill_registry is None:
        return "[ERROR] No skill registry available. Inject _skill_registry via kwargs."
    registry = _skill_registry
    skill = registry.discover().get_skill(safe_name)
    if not skill:
        try:
            available = [s["name"] for s in registry.list_skills()]
        except Exception:
            available = ["html-widgets"]
        return f"[ERROR] Skill '{safe_name}' not found. Available skills: {', '.join(available)}"

    return skill["content"]
