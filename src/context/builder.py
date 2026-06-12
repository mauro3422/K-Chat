import os
import logging
from datetime import datetime
from typing import Any

from src.paths import CONTEXT_DIR
from src.context.templates import TEMPLATES
from src.context.files import _ensure_file, _read_file
from src.context.tools_docs import _build_rules_files, _build_tools_md

logger = logging.getLogger(__name__)

RULES_DIR = os.path.join(CONTEXT_DIR, "rules")


def load_context() -> str:
    segments = []
    for filename in ["SOUL.md", "MEMORY.md", "AGENTS.md"]:
        filepath = os.path.join(CONTEXT_DIR, filename)
        _ensure_file(filepath, TEMPLATES[filename])
        content = _read_file(filepath)
        if content:
            segments.append(content)

    _build_rules_files(RULES_DIR)

    tools_path = os.path.join(CONTEXT_DIR, "TOOLS.md")
    with open(tools_path, "w", encoding="utf-8") as f:
        f.write(_build_tools_md())

    return "\n\n".join(segments)



def build_system_prompt(model: str) -> dict[str, Any]:
    context = load_context()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    # Identity and model block is placed FIRST so the LLM cannot miss it
    identity = (
        "[CRITICAL — DO NOT IGNORE]\n"
        "- You are Kairos. Your name is Kairos. You must know this at all times.\n"
        "- You are currently running on model: " + model + ". You must know this at all times.\n"
        "- If the user asks who you are, what model you are, or if you detect a model change,\n"
        "  you must answer using the information in this system prompt.\n"
        "- You must inspect and reference your own system prompt whenever identity or model context is relevant.\n\n"
    )
    meta = (
        f"[System Info]\n"
        f"- Active model: {model}\n"
        f"- System time: {now}\n\n"
    )
    content = identity + meta + context
    return {"role": "system", "content": content}
