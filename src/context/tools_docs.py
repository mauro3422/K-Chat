import os
import logging
from typing import Any

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


def _build_tools_md(tool_definitions: dict[str, Any] | None = None) -> str:
    """Generates a markdown document listing all available tools.

    The output is consumed by the system prompt to inform the LLM about
    which tools are available and how to call them.

    *tool_definitions* — injected from the caller.  When ``None`` the
    function falls back to importing from ``src.tools``.
    """
    if tool_definitions is None:
        from src.tools import get_default_registry
        tool_definitions = get_default_registry().definitions

    lines = [
        "# Available Tools",
        "",
        "These are the internal tools available directly as API function calls.",
        "",
    ]
    for name in sorted(tool_definitions.keys()):
        fn = tool_definitions[name]["function"]
        desc = fn["description"]
        lines.append(f"- **{name}**: {desc}")
        props = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])
        example_parts = []
        for pname, pdef in sorted(props.items()):
            ptype = pdef.get("type", "string")
            req_label = "required" if pname in required else "optional"
            pdesc = pdef.get("description", "")
            lines.append(f"  - `{pname}` ({ptype}) ({req_label}): {pdesc}")
            default = pdef.get("default", "")
            if ptype == "string":
                val = default or f"example {pname}"
                example_parts.append(f'{pname}="{val}"')
            else:
                val = default or 5
                example_parts.append(f"{pname}={val}")
        if example_parts:
            lines.append(f"  Example: `{name}({', '.join(example_parts)})`")
        lines.append("")
    return "\n".join(lines)


def _build_rules_files(rules_dir: str, tool_definitions: dict[str, Any] | None = None) -> None:
    """Generates rules/<tool>.md files from TOOL_DEFINITIONS.

    Each file has an auto-generated params table (regenerated on every call)
    and a manual section below '---' that is preserved across generations.

    *tool_definitions* — injected from the caller.  When ``None`` the
    function falls back to importing from ``src.tools``.
    """
    if tool_definitions is None:
        from src.tools import get_default_registry
        tool_definitions = get_default_registry().definitions

    os.makedirs(rules_dir, exist_ok=True)

    for name in sorted(tool_definitions.keys()):
        fn = tool_definitions[name]["function"]
        new_auto = _auto_section(name, fn)
        filepath = os.path.join(rules_dir, f"{name}.md")

        manual = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split(_MANUAL_SEPARATOR, 1)
            manual = parts[1] if len(parts) > 1 else ""

        new_content = new_auto
        if manual:
            new_content += _MANUAL_SEPARATOR + manual

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                old_content = f.read()
            if old_content == new_content:
                logger.debug("Skipping unchanged rule file %s", filepath)
                continue

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        logger.debug("Generated %s", filepath)
