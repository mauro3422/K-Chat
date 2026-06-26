"""Noise filter for session exchanges.

Heuristic rules to discard or flag low-value exchanges before
they reach the curator LLM. Zero tokens, pure rules.
"""

import re

# Minimum character length for an exchange to be kept
_MIN_CHARS = 50

# Keywords that indicate a purely technical/tool exchange (no semantic value)
_TOOL_PATTERNS: list[re.Pattern] = [
    re.compile(r'^\d+\.\s*\[.*?\]'),          # Numbered tool results
    re.compile(r'^(search|fetch|read|write|execute|edit)_'),
    re.compile(r'^\d+\s+files?\s+(found|matched|analyzed)'),
    re.compile(r'^(Tool|Herramienta)\s'),
    re.compile(r'^\d+\.\s*https?://'),         # URL lists
]

# Greetings / low-effort messages
_GREETING_PATTERNS: list[re.Pattern] = [
    re.compile(r'^\s*(hola|buenas|hey|ok|okey|dale|si|sí|no|gracias|okay)\s*$', re.IGNORECASE),
    re.compile(r'^\s*(ok|okey|dale)\s*,?\s*(haz|continua|sigue|prueba)\s*', re.IGNORECASE),
]

# User messages that are purely confirmations
_CONFIRMATION_WORDS = {
    'ok', 'okey', 'dale', 'si', 'sí', 'no', 'bueno', 'bien',
    'genial', 'perfecto', 'excelente', 'listo', 'hecho',
    'adelante', 'procede', 'continua', 'sigue',
}


def is_noise(text: str, role: str = "user") -> tuple[bool, str]:
    """Check if an exchange text is noise and should be filtered.

    Returns:
        (True, reason) if noise, (False, "") if valuable.
    """
    stripped = text.strip()

    # Empty or too short
    if len(stripped) < _MIN_CHARS:
        return True, f"too_short ({len(stripped)} chars < {_MIN_CHARS})"

    # Pure tool output
    for pattern in _TOOL_PATTERNS:
        if pattern.match(stripped):
            return True, "tool_output"

    # Pure greetings/confirmations
    for pattern in _GREETING_PATTERNS:
        if pattern.match(stripped):
            return True, "greeting_or_confirmation"

    # User messages that are just one word confirmations
    if role == "user":
        words = stripped.lower().split()
        if len(words) <= 3 and all(w.strip('.,!?') in _CONFIRMATION_WORDS for w in words):
            return True, "confirmation_only"

    # Remove lines that are just code blocks
    code_only = re.sub(r'```[\s\S]*?```', '', stripped).strip()
    if len(code_only) < 10:
        return True, "code_block_only"

    return False, ""



