import logging
import os

logger = logging.getLogger(__name__)

# Definición de la tool para el modelo LLM
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


def run(name=None, **kwargs) -> str:
    if name is None:
        name = kwargs.get("name", kwargs.get("skill", kwargs.get("skill_name", "")))
    _session_id = kwargs.get("_session_id")
    """Reads and returns the content of a skill from the skills/ folder."""
    # Sanitize the name to prevent directory traversal
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
    if not safe_name:
        return "[ERROR] Invalid skill name."

    from src.skills import SkillRegistry
    registry = SkillRegistry()
    skill = registry.discover().get_skill(safe_name)
    if not skill:
        # List available skills to guide the model
        try:
            available = [s["name"] for s in registry.list_skills()]
        except Exception:
            available = ["html-widgets"]
        return f"[ERROR] Skill '{safe_name}' not found. Available skills: {', '.join(available)}"

    return skill["content"]

