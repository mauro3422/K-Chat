import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

_AUTO_MARKER = "<!-- auto:params -->"
_MANUAL_SEPARATOR = "\n---\n\n"


def _format_default_cell(default: Any) -> str:
    if default is None:
        return ""
    if isinstance(default, bool):
        return "true" if default else "false"
    return str(default)


def _param_notes(pdef: dict[str, Any]) -> str:
    notes = []
    enum = pdef.get("enum")
    if enum:
        notes.append(f"Values: {', '.join(str(e) for e in enum)}")

    minimum = pdef.get("minimum")
    maximum = pdef.get("maximum")
    if minimum is not None or maximum is not None:
        if minimum is not None and maximum is not None:
            notes.append(f"Range: {minimum}..{maximum}")
        elif minimum is not None:
            notes.append(f"Minimum: {minimum}")
        else:
            notes.append(f"Maximum: {maximum}")

    if not notes:
        return ""
    return " " + " ".join(notes)


def _example_value(pname: str, pdef: dict[str, Any]) -> str:
    ptype = pdef.get("type", "string")
    default = pdef.get("default", None)

    if ptype == "string":
        val = default if default not in (None, "") else f"example {pname}"
        return f'{pname}="{val}"'

    if ptype == "boolean":
        if default is None:
            val = "false"
        else:
            val = "true" if bool(default) else "false"
        return f"{pname}={val}"

    if default is not None:
        return f"{pname}={default}"

    return f"{pname}=5"


def _auto_section(name: str, fn: dict) -> str:
    """Generate the auto-generated param section for a tool rule file."""
    desc = fn["description"]
    props = fn.get("parameters", {}).get("properties", {})
    required = fn.get("parameters", {}).get("required", [])
    lines = [
        f"# {name}",
        f"**{desc}**\n",
        _AUTO_MARKER,
        "| Par\u00e1metro | Tipo | Requerido | Default | Descripci\u00f3n |",
        "|---|---|---|---|---|",
    ]
    for pname, pdef in sorted(props.items()):
        ptype = pdef.get("type", "string")
        req = "S\u00ed" if pname in required else "No"
        default = _format_default_cell(pdef.get("default", ""))
        pdesc = pdef.get("description", "")
        pdesc += _param_notes(pdef)
        lines.append(f"| `{pname}` | {ptype} | {req} | {default} | {pdesc} |")
    return "\n".join(lines) + "\n"


def _build_tools_md(tool_definitions: dict[str, Any]) -> str:
    """Generate a markdown document listing all available tools.

    The output is consumed by the system prompt to inform the LLM about
    which tools are available and how to call them.

    *tool_definitions* - required injection from the caller.
    """

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
            pdesc += _param_notes(pdef)
            lines.append(f"  - `{pname}` ({ptype}) ({req_label}): {pdesc}")
            example_parts.append(_example_value(pname, pdef))
        if example_parts:
            lines.append(f"  Example: `{name}({', '.join(example_parts)})`")
        lines.append("")
    return "\n".join(lines)


def _build_rules_files(rules_dir: str, tool_definitions: dict[str, Any]) -> None:
    """Generate rules/<tool>.md files from TOOL_DEFINITIONS.

    Each file has an auto-generated params table (regenerated on every call)
    and a manual section below '---' that is preserved across generations.

    *tool_definitions* - required injection from the caller.
    """

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
