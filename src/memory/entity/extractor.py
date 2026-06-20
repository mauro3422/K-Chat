import logging
import re
import os
import threading
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

_LEXICON: dict[str, set[str]] = {
    'tecnologia': {
        'python', 'rust', 'c++', 'javascript', 'typescript', 'go',
        'fastapi', 'sqlite', 'sqlite-vec', 'fastembed',
        'hyprland', 'wayland', 'kitty', 'wofi', 'pulseaudio',
        'systemd', 'git', 'github', 'docker', 'vite', 'playwright',
        'pytest', 'node.js', 'react', 'nvim', 'vscode',
        'hyprpaper', 'mako', 'dunst', 'ffmpeg', 'opengl', 'egl',
        'waybar', 'lua', 'pseint', 'sfml', 'glfw', 'bash',
    },
    'proyecto': {
        'k-chat', 'survivoros', 'rawsuros', 'neopse',
        'duckrubbersugar', 'conmap', 'structura', 'omnysys',
        'coral-engine', 'widgetforge', 'gitteach', 'orchstorm',
        'llama.cpp', 'searxng',
    },
    'persona': {
        'mauro', 'kairos', 'sabrina',
    },
    'lenguaje': {
        'pseudocódigo', 'pseint',
    },
    'lugar': {
        'tucumán', 'argentina',
    },
    'tema': set(),
}

_TEMA_KEYWORDS = [
    'arquitectura', 'streaming', 'widgets', 'memoria',
    'embeddings', 'testing', 'deploy', 'rendering',
    'performance', 'seguridad', 'api', 'ui', 'backend',
    'frontend', 'database', 'kernel', 'graphics', 'audio',
    'networking', 'paralelismo', 'concurrencia',
]

_TEMA_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in _TEMA_KEYWORDS
]

_PERSONA_PATTERN = re.compile(
    r'(?<!\w)(?:de|por|para|con|según|a|como|del)[ \t]+'
    r'([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)(?!\w)',
)

_PROYECTO_SUFFIX = re.compile(
    r'\b([A-ZÁÉÍÓÚÑ][a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]*(?:OS|ER|OR))\b',
)

_PROYECTO_MENTION = re.compile(
    r'(?:[Pp]royecto|[Rr]epo|[Ss]istema)[ \t]+'
    r'([A-ZÁÉÍÓÚÑ][a-zA-ZáéíóúñÁÉÍÓÚÑ0-9_-]+)',
)

_LUGAR_PATTERN = re.compile(
    r'\ben[ \t]+'
    r'([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)',
)

_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    ('persona', _PERSONA_PATTERN, 0.7),
    ('proyecto', _PROYECTO_SUFFIX, 0.7),
    ('proyecto', _PROYECTO_MENTION, 0.7),
    ('lugar', _LUGAR_PATTERN, 0.7),
]

_EXCLUDED_WORDS = {
    # Spanish common words (false positives for entity extraction)
    'los', 'son', 'uno', 'una', 'todo', 'cada', 'más', 'sin',
    'de', 'en', 'el', 'la', 'un', 'que', 'del', 'al', 'por',
    'con', 'su', 'le', 'ya', 'este', 'entre', 'para', 'como',
    'muy', 'era', 'tan', 'ser', 'esa', 'ese', 'eso', 'sus',
    'las', 'les', 'nos', 'os', 'se', 'me', 'te', 'lo', 'ha',
    'he', 'has', 'han', 'hay', 'fue', 'era', 'sido', 'está',
    'estoy', 'están', 'estaba', 'estado', 'tiene', 'tenía',
    'hace', 'hacia', 'dice', 'dijo', 'voy', 'vas', 'va',
    'usan', 'usar', 'usando', 'crea', 'creo', 'crear',
    'tipo', 'parte', 'forma', 'vez', 'tiempo', 'día', 'días',
    'cosa', 'cosas', 'algo', 'nada', 'cada', 'si', 'no',
    # English common words
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all',
    'can', 'had', 'her', 'was', 'one', 'our', 'out', 'has',
    'have', 'been', 'some', 'same', 'also', 'its', 'than',
    'them', 'they', 'into', 'over', 'such', 'that', 'this',
    'with', 'will', 'would', 'about', 'their', 'there',
    'these', 'those', 'which', 'while', 'should', 'could',
    'other', 'after', 'before', 'between', 'just', 'like',
    'more', 'most', 'much', 'only', 'very', 'well', 'what',
    'when', 'where', 'why',
}

_REMOVE_PATTERNS = [
    re.compile(r'```.*?```', re.DOTALL),
    re.compile(r'`[^`]+`'),
    re.compile(r'https?://\S+'),
]

_ALL_KNOWN: set[str] = set()
for entries in _LEXICON.values():
    _ALL_KNOWN.update(entries)

_SYNONYMS: dict[str, str] = {
    "python3": "python",
    "python2": "python",
    "js": "javascript",
    "ts": "typescript",
    "c++": "cpp",
    "cxx": "cpp",
    "reactjs": "react",
    "nextjs": "next",
    "nodejs": "node",
    "github": "git",
}

_LEARNED_ENTITIES: dict[str, set[str]] = defaultdict(set)
_CANDIDATE_FREQ: dict[str, int] = {}
_LEARNED_COUNT_SINCE_SAVE: int = 0
_entities_lock = threading.Lock()


def _tokenize(text: str) -> str:
    for pattern in _REMOVE_PATTERNS:
        text = pattern.sub(' ', text)
    return text.lower()


def _find_words(text: str) -> list[str]:
    for pattern in _REMOVE_PATTERNS:
        text = pattern.sub(' ', text)
    tokens = text.split()
    words = []
    for token in tokens:
        word = token.strip('.,;:!?()[]{}""''«»‹›“”‘’「」『』【】《》<>')
        if word:
            words.append(word)
    return words


def canonical_name(name: str) -> str:
    lower = name.lower()
    return _SYNONYMS.get(lower, name)


def learn_from_text(text: str) -> None:
    with _entities_lock:
        global _LEARNED_COUNT_SINCE_SAVE
        words = _find_words(text)
        for word in words:
            if len(word) < 3:
                continue
            lower = word.lower()
            if lower in _EXCLUDED_WORDS:
                continue
            if lower in _ALL_KNOWN:
                continue
            if not (word[0].isupper() or word.isupper()):
                continue
            if lower in _CANDIDATE_FREQ:
                _CANDIDATE_FREQ[lower] += 1
            else:
                _CANDIDATE_FREQ[lower] = 1
            if _CANDIDATE_FREQ[lower] >= 3:
                already_learned = {e.lower() for s in _LEARNED_ENTITIES.values() for e in s}
                if lower not in already_learned:
                    if _PROYECTO_SUFFIX.search(word):
                        _LEARNED_ENTITIES["proyecto"].add(word)
                    else:
                        _LEARNED_ENTITIES["tecnologia"].add(word)
                    _LEARNED_COUNT_SINCE_SAVE += 1
                    if _LEARNED_COUNT_SINCE_SAVE >= 10:
                        save_learned_entities()


def save_learned_entities(filepath: Optional[str] = None) -> None:
    with _entities_lock:
        import json
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "learned_entities.json")
        data = {
            "learned": {k: list(v) for k, v in _LEARNED_ENTITIES.items()},
            "freq": dict(_CANDIDATE_FREQ),
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)


def load_learned_entities(filepath: Optional[str] = None) -> None:
    with _entities_lock:
        import json
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "learned_entities.json")
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath) as f:
                data = json.load(f)
            for etype, entities in data.get("learned", {}).items():
                _LEARNED_ENTITIES[etype].update(entities)
            _CANDIDATE_FREQ.update(data.get("freq", {}))
        except Exception:
            logger.warning("Failed to load learned entities", exc_info=True)


def extract_entities(text: str) -> list[tuple[str, str, float]]:
    seen: set[tuple[str, str]] = set()
    results: list[tuple[str, str, float]] = []
    words = _find_words(text)

    for word in words:
        canonical = canonical_name(word)
        lower = canonical.lower()
        for etype, entries in _LEXICON.items():
            if lower in entries:
                key = (etype, lower)
                if key not in seen:
                    seen.add(key)
                    results.append((etype, canonical, 1.0))

    for etype, pattern, confidence in _PATTERNS:
        for match in pattern.finditer(text):
            entity = match.group(1)
            canonical = canonical_name(entity)
            lower = canonical.lower()
            if lower in _EXCLUDED_WORDS:
                continue
            if lower in _ALL_KNOWN:
                continue
            key = (etype, lower)
            if key not in seen:
                seen.add(key)
                results.append((etype, canonical, confidence))

    for pattern, keyword in zip(_TEMA_PATTERNS, _TEMA_KEYWORDS):
        if pattern.search(text):
            key = ('tema', keyword)
            if key not in seen:
                seen.add(key)
                results.append(('tema', keyword, 1.0))

    lower_words = set(w.lower() for w in words)
    with _entities_lock:
        for etype, learned_set in _LEARNED_ENTITIES.items():
            for entity in learned_set:
                if entity.lower() in lower_words:
                    key = (etype, entity.lower())
                    if key not in seen:
                        seen.add(key)
                        results.append((etype, entity, 0.6))

    results.sort(key=lambda x: (-x[2], x[0], x[1]))
    return results


load_learned_entities()
