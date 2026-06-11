import os
import logging

logger = logging.getLogger(__name__)

_AUTO_MARKER = "<!-- auto:params -->"
_MANUAL_SEPARATOR = "\n---\n\n"

def _auto_section(name: str, fn: dict) -> str:
    """Generates the auto-generated param section for a tool rule file."""
    desc = fn["description"]
    props = fn.get("parameters", {}).get("properties", {})
    required = fn.get("parameters", {}).get("required", [])
    lines = [
        f"# {name}",
        f"**{desc}**\n",
        _AUTO_MARKER,
        "| Parámetro | Tipo | Requerido | Default | Descripción |",
        "|---|---|---|---|---|",
    ]
    for pname, pdef in sorted(props.items()):
        ptype = pdef.get("type", "string")
        req = "Sí" if pname in required else "No"
        default = pdef.get("default", "")
        pdesc = pdef.get("description", "")
        enum = pdef.get("enum")
        if enum:
            pdesc += f" Valores: {', '.join(str(e) for e in enum)}"
        lines.append(f"| `{pname}` | {ptype} | {req} | {default} | {pdesc} |")
    return "\n".join(lines) + "\n"


def _build_rules_files(rules_dir: str) -> None:
    """Generates rules/<tool>.md files from TOOL_DEFINITIONS.
    
    Each file has an auto-generated params table (regenerated on every call)
    and a manual section below '---' that is preserved across generations.
    """
    from src.tools import TOOL_DEFINITIONS
    os.makedirs(rules_dir, exist_ok=True)
    
    for name in sorted(TOOL_DEFINITIONS.keys()):
        fn = TOOL_DEFINITIONS[name]["function"]
        new_auto = _auto_section(name, fn)
        filepath = os.path.join(rules_dir, f"{name}.md")
        
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            # Preserve manual section (everything after the first ---)
            parts = content.split(_MANUAL_SEPARATOR, 1)
            manual = parts[1] if len(parts) > 1 else ""
        else:
            manual = ""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_auto)
            if manual:
                f.write(_MANUAL_SEPARATOR + manual)
        
        logger.debug("Generated %s", filepath)
