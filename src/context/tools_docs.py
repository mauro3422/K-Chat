def _build_tools_md() -> str:
    """Generates TOOLS.md with all available tools and their parameters."""
    from src.tools import TOOL_DEFINITIONS
    lines = ["# Available Tools\n"]
    lines.append("These are the internal tools available via `execute_action(action_name=..., arguments=...)`.\n")
    for name in sorted(TOOL_DEFINITIONS.keys()):
        fn = TOOL_DEFINITIONS[name]["function"]
        desc = fn["description"]
        props = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])
        example_args = []
        for pname, pdef in props.items():
            ptype = pdef.get("type", "string")
            if ptype == "string":
                example_val = f'"example {pname}"'
            elif ptype == "integer":
                example_val = "5"
            else:
                example_val = f'"{pname}"'
            req_marker = " (required)" if pname in required else " (optional)"
            example_args.append(f'{pname}={example_val}{req_marker}')
        example = f"{name}({', '.join(example_args)})" if example_args else f"{name}()"
        lines.append(f"- **{name}**: {desc}")
        lines.append(f"  Example: `{example}`")
        if props:
            lines.append("  Parameters:")
            for pname, pdef in props.items():
                ptype = pdef.get("type", "string")
                pdesc = pdef.get("description", "")
                req = "(required)" if pname in required else "(optional)"
                lines.append(f"    - `{pname}` ({ptype}) {req}: {pdesc}")
    return "\n".join(lines)
