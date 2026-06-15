"""_preflight: pre/post-flight checks para edits seguros.

Módulo Lego privado — no depende de tools ni de core.
Solo importa stdlib + _validators.py.

Prevents: tag corruption, duplicate code, broken syntax, lost functions.

Usage:
    from src.tools._preflight import preflight_check, postflight_check, rollback
"""

import os
import re
import shutil
import tempfile
from typing import Any


# ─── HTML TAG BALANCE ─────────────────────────────────────────────────

_HTML_SELF_CLOSING = frozenset([
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
])

_HTML_VOID = _HTML_SELF_CLOSING  # same set

_TAG_RE = re.compile(r'<(/?)(\w[\w-]*)[^>]*?' + r'(/?)>')


def check_html_balance(content: str) -> list[str]:
    """Check HTML tag balance. Returns list of errors (empty = OK)."""
    stack: list[str] = []
    errors: list[str] = []
    for m in _TAG_RE.finditer(content):
        is_close = m.group(1) == '/'
        tag_name = m.group(2).lower()
        is_self = m.group(3) == '/' or tag_name in _HTML_SELF_CLOSING
        if is_self:
            continue
        if is_close:
            if not stack:
                errors.append(f"Unexpected closing </{tag_name}> without matching open")
            elif stack[-1] != tag_name:
                errors.append(f"Mismatched: expected </{stack[-1]}>, found </{tag_name}>")
            else:
                stack.pop()
        else:
            stack.append(tag_name)
    for tag in stack:
        errors.append(f"Unclosed <{tag}> (missing </{tag}>)")
    return errors


# ─── JS/CSS BRACE BALANCE ─────────────────────────────────────────────

def check_brace_balance(content: str) -> list[str]:
    """Check brace/paren/bracket balance for JS, CSS, TS. Returns errors."""
    stack: list[str] = []
    errors: list[str] = []
    in_string = False
    string_char = ''
    in_comment = False
    in_line_comment = False
    prev = ''

    for ch in content:
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            continue
        if in_comment:
            if prev == '*' and ch == '/':
                in_comment = False
            prev = ch
            continue
        if in_string:
            if ch == string_char and prev != '\\':
                in_string = False
            prev = ch
            continue

        if ch == '/' and prev == '/':
            in_line_comment = True
            if stack and stack[-1] == '/':
                stack.pop()
            continue
        if ch == '*' and prev == '/':
            in_comment = True
            if stack and stack[-1] == '/':
                stack.pop()
            continue
        if ch in ('"', "'", '`'):
            in_string = True
            string_char = ch
            prev = ch
            continue
        if ch in ('{', '(', '['):
            stack.append(ch)
        elif ch == '}':
            if not stack:
                errors.append("Unexpected '}' without matching '{'")
            elif stack[-1] != '{':
                errors.append(f"Mismatched: expected closing for '{stack[-1]}', found '}}'")
            else:
                stack.pop()
        elif ch == ')':
            if not stack:
                errors.append("Unexpected ')' without matching '('")
            elif stack[-1] != '(':
                errors.append(f"Mismatched: expected closing for '{stack[-1]}', found ')'")
            else:
                stack.pop()
        elif ch == ']':
            if not stack:
                errors.append("Unexpected ']' without matching '['")
            elif stack[-1] != '[':
                errors.append(f"Mismatched: expected closing for '{stack[-1]}', found ']'")
            else:
                stack.pop()
        prev = ch

    for opener in reversed(stack):
        names = {'{': '}', '(': ')', '[': ']'}
        errors.append(f"Unclosed '{opener}' (missing '{names.get(opener, '?')}')")
    return errors


# ─── PYTHON CHECKS ────────────────────────────────────────────────────

def check_python_structure(content: str) -> list[str]:
    """Check Python-specific issues: indentation, duplicate lines."""
    errors: list[str] = []
    lines = content.split('\n')
    prev_line = ''
    dup_count = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            prev_line = stripped
            continue
        if stripped == prev_line and stripped:
            dup_count += 1
            if dup_count >= 2:
                errors.append(f"Line {i}: duplicate consecutive line '{stripped[:60]}'")
        else:
            dup_count = 0
        prev_line = stripped
    return errors


# ─── GENERIC CHECKS ───────────────────────────────────────────────────

def check_duplicate_lines(content: str) -> list[str]:
    """Detect 3+ consecutive identical non-empty lines."""
    errors: list[str] = []
    lines = content.split('\n')
    streak = 1
    for i in range(1, len(lines)):
        if lines[i].strip() and lines[i].strip() == lines[i-1].strip():
            streak += 1
        else:
            if streak >= 3:
                errors.append(f"Lines {i-streak+1}-{i}: '{lines[i-1].strip()[:50]}' repeated {streak} times")
            streak = 1
    if streak >= 3:
        errors.append(f"Lines {len(lines)-streak+1}-{len(lines)}: repeated {streak} times")
    return errors


def check_dangerous_deletions(original_lines: list[str], start: int, end: int) -> list[str]:
    """Warn if the edit range includes critical lines."""
    warnings: list[str] = []
    for i in range(start - 1, min(end, len(original_lines))):
        line = original_lines[i].strip()
        if not line:
            continue
        # Detect closing tags being deleted
        if re.match(r'^</(div|script|style|main|aside|section|article|body|html)\s*>', line):
            warnings.append(f"Line {i+1}: deleting closing tag '{line[:40]}' — may break HTML structure")
        # Detect function/class defs being deleted
        if re.match(r'^(async\s+)?(def|class)\s+\w+', line):
            warnings.append(f"Line {i+1}: deleting definition '{line[:60]}'")
        # Detect return statements
        if line.startswith('return ') or line == 'return':
            warnings.append(f"Line {i+1}: deleting return statement")
        # Detect import statements
        if line.startswith('import ') or line.startswith('from '):
            warnings.append(f"Line {i+1}: deleting import '{line[:60]}'")


    return warnings


# ─── PREFLIGHT ────────────────────────────────────────────────────────

def preflight_check(
    path: str,
    start_line: int,
    end_line: int | None,
    new_content: str,
) -> dict[str, Any]:
    """Run pre-flight checks before applying an edit.

    Returns:
        {
            "ok": bool,
            "warnings": [...],
            "dangerous": [...],  # blocks that should prevent edit
            "lines_touched": [line_numbers],
            "preview": "first 5 lines of new_content",
        }
    """
    result: dict[str, Any] = {
        "ok": True,
        "warnings": [],
        "dangerous": [],
        "lines_touched": [],
        "preview": "",
    }

    if not os.path.isfile(path):
        return result

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        return result

    # Lines being touched
    if end_line is not None:
        s = max(1, min(start_line, end_line))
        e = min(len(lines), max(start_line, end_line))
        result["lines_touched"] = list(range(s, e + 1))
        result["warnings"].extend(check_dangerous_deletions(lines, s, e))
    else:
        result["lines_touched"] = [start_line]

    # Preview of new content
    preview_lines = new_content.split('\n')[:5]
    result["preview"] = '\n'.join(preview_lines)

    # Language-specific checks on new content
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.html', '.htm'):
        html_errors = check_html_balance(new_content)
        for e in html_errors:
            result["warnings"].append(f"HTML balance: {e}")
    elif ext in ('.js', '.ts', '.jsx', '.tsx', '.css'):
        brace_errors = check_brace_balance(new_content)
        for e in brace_errors:
            result["warnings"].append(f"Brace balance: {e}")
    elif ext == '.py':
        py_errors = check_python_structure(new_content)
        for e in py_errors:
            result["warnings"].append(f"Python: {e}")

    # Generic duplicate check
    dup_errors = check_duplicate_lines(new_content)
    for e in dup_errors:
        result["warnings"].append(f"Duplicate: {e}")

    if result["warnings"]:
        result["ok"] = False  # warnings = not OK, but not blocking

    return result


# ─── POSTFLIGHT ───────────────────────────────────────────────────────

def postflight_check(path: str, content: str | None = None) -> dict[str, Any]:
    """Run post-flight checks after writing a file.

    Returns:
        {"ok": bool, "errors": [...], "warnings": [...]}
    """
    result: dict[str, Any] = {"ok": True, "errors": [], "warnings": []}

    if content is None:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            return {"ok": False, "errors": [f"Cannot read file: {e}"], "warnings": []}

    ext = os.path.splitext(path)[1].lower()

    # Syntax validation
    if ext == '.py':
        from src.tools._validators import validate_python
        v = validate_python(content, path)
        if v['status'] == 'error':
            result["errors"].append(f"Python: {v['message']}")
    elif ext in ('.js', '.ts', '.jsx', '.tsx'):
        from src.tools._validators import validate_javascript
        v = validate_javascript(content, path)
        if v['status'] == 'error':
            result["errors"].append(f"JS: {v['message']}")
    elif ext == '.json':
        from src.tools._validators import validate_json
        v = validate_json(content, path)
        if v['status'] == 'error':
            result["errors"].append(f"JSON: {v['message']}")
    elif ext == '.html':
        html_errors = check_html_balance(content)
        for e in html_errors:
            result["errors"].append(f"HTML: {e}")
    elif ext in ('.css',):
        brace_errors = check_brace_balance(content)
        for e in brace_errors:
            result["errors"].append(f"CSS: {e}")

    # Duplicate line check
    dup_errors = check_duplicate_lines(content)
    for e in dup_errors:
        result["warnings"].append(f"Duplicate: {e}")

    if result["errors"]:
        result["ok"] = False

    return result


# ─── BACKUP / ROLLBACK ────────────────────────────────────────────────

def create_backup(path: str) -> str | None:
    """Create a backup of the file before editing. Returns backup path."""
    try:
        backup_dir = tempfile.mkdtemp(prefix="kairos_preflight_")
        backup_path = os.path.join(backup_dir, os.path.basename(path))
        shutil.copy2(path, backup_path)
        return backup_path
    except Exception:
        return None


def rollback(path: str, backup_path: str) -> bool:
    """Restore file from backup. Returns True on success."""
    try:
        shutil.copy2(backup_path, path)
        # Clean up backup
        backup_dir = os.path.dirname(backup_path)
        shutil.rmtree(backup_dir, ignore_errors=True)
        return True
    except Exception:
        return False
