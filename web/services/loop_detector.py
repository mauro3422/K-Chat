import logging

logger = logging.getLogger(__name__)

LOOP_WINDOW_SIZE = 15
LOOP_PHRASE_REPEATS = 6


class LoopDetector:
    """Detect repeated tokens or phrases that indicate the model is stuck."""

    def __init__(self):
        self._recent_tokens: list[str] = []
        self._recent_text: str = ""

    def check(self, token: str) -> str | None:
        self._recent_tokens.append(token)
        if len(self._recent_tokens) > LOOP_WINDOW_SIZE:
            self._recent_tokens = self._recent_tokens[-LOOP_WINDOW_SIZE:]

        if len(self._recent_tokens) >= LOOP_WINDOW_SIZE:
            if len(set(self._recent_tokens)) == 1 and self._recent_tokens[0].strip():
                return f"Loop detectado: mismo token repetido {LOOP_WINDOW_SIZE} veces"

        self._recent_text += token
        if len(self._recent_text) > 2000:
            self._recent_text = self._recent_text[-1000:]

        # Skip phrase repetition check inside html-widget code blocks
        # (CSS/HTML formatting repeats legitimately in widget templates)
        if self._inside_code_block():
            return None

        for phrase_len in [50, 100, 200]:
            if len(self._recent_text) >= phrase_len * LOOP_PHRASE_REPEATS:
                phrase = self._recent_text[-phrase_len:]
                count = self._recent_text.count(phrase)
                if count >= LOOP_PHRASE_REPEATS and len(phrase.strip()) > 10:
                    return f"Loop detectado: frase de {phrase_len} chars repetida {count} veces"

        return None

    def _inside_code_block(self) -> bool:
        last_open = self._recent_text.rfind('```html-widget')
        if last_open < 0:
            return False
        # Check if there's a closing ``` after the opening
        after_open = self._recent_text[last_open + 3:]
        return '```' not in after_open
