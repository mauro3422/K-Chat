import os
from datetime import datetime
from src.tools import TOOLS

CONTEXT_DIR = os.path.dirname(os.path.dirname(__file__))

USER_LANG = "espanol"
USER_NAME = ""
SYS_OPERATOR = os.environ.get("USER") or os.environ.get("USERNAME", "user")

TEMPLATES = {
    "SOUL.md": "# SOUL.md\n\n- Kairos\n\nYou are a personal assistant. You respond directly and concisely. Friendly tone, not corporate.\n",
    "MEMORY.md": f"# MEMORY.md\n\nUser: {USER_NAME}\nSystem: {SYS_OPERATOR}\n",
    "AGENTS.md": (
        "# AGENTS.md\n\n"
        "Agent rules:\n"
        "- Think step by step in English before responding\n"
        f"- Final answer must be entirely in {USER_LANG}. Never output English sentences, commentary, or meta-text in the response content. Reasoning is internal — the content part must be 100% in {USER_LANG}.\n"
        "- Be direct and concise\n"
        "- Never make up information\n"
        "- Ask for clarification if context is missing\n"
        "- When user asks for current/recent information or Google data -> USE web_search immediately\n"
        "- You can call MULTIPLE tools in a single turn, don't wait for permission\n"
        "- Do NOT announce tool calls (\"let me search\", \"I'll look that up\", \"voy a buscar\") — CALL the tool directly and silently\n"
        "- For complex questions, make MULTIPLE specific searches\n"
        "- In FOLLOW-UP turns, if you need more info, call web_search again — do NOT describe what you would search, just SEARCH\n"
        "- Never output tool names or queries as text. Either call the tool via the API or don't mention it\n"
        "- If a tool returns [ERROR], tell the user and suggest an alternative\n"
    ),
}

def _build_tools_md() -> str:
    lines = ["# TOOLS.md\n"]
    for t in TOOLS:
        fn = t["function"]
        name = fn["name"]
        desc = fn["description"]
        params = fn.get("parameters", {}).get("properties", {})
        args_line = ", ".join(params.keys()) if params else "none"
        lines.append(f"- **{name}**: {desc}")
        lines.append(f"  Arguments: {args_line}")
    return "\n".join(lines)

def load_context():
    segments = []
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(TEMPLATES[filename])
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                segments.append(content)

    tools_md_path = os.path.join(CONTEXT_DIR, "TOOLS.md")
    tools_md = _build_tools_md()
    with open(tools_md_path, "w", encoding="utf-8") as f:
        f.write(tools_md)
    segments.append(tools_md)

    return "\n\n".join(segments)

def build_system_prompt(model: str) -> dict:
    context = load_context()
    content = f"[System: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Model: {model}]\nThink in English. Respond in {USER_LANG}.\n\n{context}"
    return {"role": "system", "content": content}
