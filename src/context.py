import os
import logging
from datetime import datetime
from textwrap import dedent

logger = logging.getLogger(__name__)

CONTEXT_DIR = os.path.dirname(os.path.dirname(__file__))

USER_LANG = "espanol"
USER_NAME = ""
SYS_OPERATOR = os.environ.get("USER") or os.environ.get("USERNAME", "user")

TEMPLATES = {
    "SOUL.md": dedent("""\
        # SOUL.md

        - Kairos

        You are a personal assistant. You respond directly and concisely. Friendly tone, not corporate.
    """),
    "MEMORY.md": f"# MEMORY.md\n\nUser: {USER_NAME}\nSystem: {SYS_OPERATOR}\n",
    "AGENTS.md": dedent(f"""\
        # AGENTS.md

        Agent rules:
        - Think step by step in English before responding
        - Final answer must be entirely in {USER_LANG}. Never output English sentences, commentary, or meta-text in the response content. Reasoning is internal — the content part must be 100% in {USER_LANG}.
        - Be direct and concise
        - Never make up information
        - Ask for clarification if context is missing
        - When user asks for current/recent information or Google data -> USE web_search immediately
        - You can call MULTIPLE tools in a single turn, don't wait for permission
        - Do NOT announce tool calls ("let me search", "I'll look that up", "voy a buscar") — CALL the tool directly and silently
        - For complex questions, make MULTIPLE specific searches
        - In FOLLOW-UP turns, if you need more info, call web_search again — do NOT describe what you would search, just SEARCH
        - Never output tool names or queries as text. Either call the tool via the API or don't mention it
        - If a tool returns [ERROR], tell the user and suggest an alternative
    """),
}


def _ensure_file(path: str, template: str) -> None:
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(template)
    except OSError as e:
        logger.warning("No se pudo crear %s: %s", path, e)


def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError as e:
        logger.warning("No se pudo leer %s: %s", path, e)
        return ""


def _build_tools_md() -> str:
    """Genera TOOLS.md con ejemplos concretos de invocación para guiar al modelo."""
    from src.tools import TOOLS
    lines = ["# Tools disponibles\n"]
    lines.append("Usa estas tools via function calling con los parámetros indicados.\n")
    for t in TOOLS:
        fn = t["function"]
        name = fn["name"]
        desc = fn["description"]
        props = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])
        # Construir ejemplo concreto con valores ilustrativos
        example_args = []
        for pname, pdef in props.items():
            ptype = pdef.get("type", "string")
            if ptype == "string":
                example_val = f'"{pname} de ejemplo"'
            elif ptype == "integer":
                example_val = "5"
            else:
                example_val = f'"{pname}"'
            req_marker = " (requerido)" if pname in required else " (opcional)"
            example_args.append(f'{pname}={example_val}{req_marker}')
        example = f"{name}({', '.join(example_args)})" if example_args else f"{name}()"
        lines.append(f"- **{name}**: {desc}")
        lines.append(f"  Ejemplo: `{example}`")
    return "\n".join(lines)


def load_context() -> str:
    segments = []
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        _ensure_file(filepath, TEMPLATES[filename])
        content = _read_file(filepath)
        if content:
            segments.append(content)

    tools_md_path = os.path.join(CONTEXT_DIR, "TOOLS.md")
    tools_md = _build_tools_md()
    try:
        with open(tools_md_path, "w", encoding="utf-8") as f:
            f.write(tools_md)
    except OSError as e:
        logger.warning("No se pudo escribir %s: %s", tools_md_path, e)
    # TOOLS.md se guarda en disco pero NO se inyecta al system prompt.
    # El modelo recibe el schema exacto via parametro tools= de la API.
    # Inyectarlo en texto causa que el modelo reproduzca ejemplos en su razonamiento
    # como bloques XML/JSON que la API de OpenCode interpreta como tool calls reales.

    return "\n\n".join(segments)



def build_system_prompt(model: str) -> dict:
    context = load_context()
    content = f"[System: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Model: {model}]\nThink in English. Respond in {USER_LANG}.\n\n{context}"
    return {"role": "system", "content": content}
