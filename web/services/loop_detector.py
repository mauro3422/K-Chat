import logging

logger = logging.getLogger(__name__)

LOOP_WINDOW_SIZE = 15
LOOP_PHRASE_REPEATS = 6


class LoopDetector:
    """Detect repeated tokens or phrases that indicate the model is stuck."""

    def __init__(self):
        self._recent_tokens: list[str] = []
        self._recent_text: str = ""
        self._total_backticks: int = 0
        self._is_widget_mode: bool = False

    def check(self, token: str) -> str | None:
        self._recent_tokens.append(token)
        if len(self._recent_tokens) > LOOP_WINDOW_SIZE:
            self._recent_tokens = self._recent_tokens[-LOOP_WINDOW_SIZE:]

        if "html-widget" in token:
            self._is_widget_mode = True

        old_count = self._recent_text.count('```')
        self._recent_text += token
        new_count = self._recent_text.count('```')
        self._total_backticks += (new_count - old_count)

        if len(self._recent_text) > 2000:
            self._recent_text = self._recent_text[-1000:]

        # Token check: same word 15+ times in a row — always a loop
        if len(self._recent_tokens) >= LOOP_WINDOW_SIZE:
            if len(set(self._recent_tokens)) == 1 and self._recent_tokens[0].strip():
                return f"Loop detectado: mismo token repetido {LOOP_WINDOW_SIZE} veces"

        # Phrase repetition check: skipped inside ANY unclosed code block or if widget mode is active
        # (CSS/HTML/code formatting repeats legitimately in templates and widgets)
        if not self._inside_code_block() and not self._is_widget_mode:
            for phrase_len in [50, 100, 200]:
                if len(self._recent_text) >= phrase_len * LOOP_PHRASE_REPEATS:
                    phrase = self._recent_text[-phrase_len:]
                    count = self._recent_text.count(phrase)
                    if count >= LOOP_PHRASE_REPEATS and len(phrase.strip()) > 10:
                        return f"Loop detectado: frase de {phrase_len} chars repetida {count} veces"

        return None

    def _inside_code_block(self) -> bool:
        return self._total_backticks % 2 == 1

