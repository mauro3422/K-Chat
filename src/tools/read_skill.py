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


def run(**kwargs) -> str:
    name = kwargs.get("name", kwargs.get("skill", kwargs.get("skill_name", "")))
    _session_id = kwargs.get("_session_id")
    """Reads and returns the content of a skill from the skills/ folder."""
    # Sanitize the name to prevent directory traversal
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
    if not safe_name:
        return "[ERROR] Invalid skill name."

    # Get the absolute path of the skills/ folder
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    skills_dir = os.path.join(base_dir, "skills")
    file_path = os.path.join(skills_dir, f"{safe_name}.md")

    if not os.path.exists(file_path):
        # List available skills to guide the model
        try:
            files = os.listdir(skills_dir)
            available = [os.path.splitext(f)[0] for f in files if f.endswith(".md") and f != "INDEX.md"]
        except Exception:
            logger.exception("Failed to list skills directory: %s", skills_dir)
            available = ["html-widgets"]

        return f"[ERROR] Skill '{safe_name}' not found. Available skills: {', '.join(available)}"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return f"[ERROR] Could not read the skill '{safe_name}'."
