"""Anti-regression tests for architectural and frontend bugs.

These tests exist to PREVENT the bugs we fixed today from coming back:
1. CSP missing blob: in img-src  → image paste previews blocked
2. Model discovery timeout in lifespan (get_verified_models without timeout)
3. Rate limit tracking integration
4. Undefined JS variable (`ext`) in message-renderer.js
5. Missing initialization calls in app.js (initSessionPage, ChatForm.init, etc.)
6. Missing imports in app.js

These read the source files directly — no DB, no fixtures, no asyncio.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# 1. CSP: blob: must be allowed in img-src
# ═══════════════════════════════════════════════════════════════════════

def test_csp_includes_blob_for_img_src() -> None:
    content = _read("web/app_factory.py")
    assert "img-src 'self' data: blob:" in content, \
        "CSP missing blob: in img-src — blocked image paste previews!"


# ═══════════════════════════════════════════════════════════════════════
# 2. Lifespan: get_verified_models must have timeout
# ═══════════════════════════════════════════════════════════════════════

def test_lifespan_has_timeout_on_get_verified_models() -> None:
    content = _read("web/app_factory.py")
    assert "asyncio.wait_for(get_verified_models(), timeout=10)" in content, \
        "Missing timeout on get_verified_models in lifespan — server startup hangs!"
    assert "asyncio.TimeoutError" in content, \
        "Missing TimeoutError handler in lifespan!"


# ═══════════════════════════════════════════════════════════════════════
# 3. Rate limit store integrated into failover
# ═══════════════════════════════════════════════════════════════════════

def test_rate_limit_store_imported_in_failover() -> None:
    content = _read("src/llm/failover.py")
    assert "get_rate_limit_store" in content, \
        "Rate limit store not imported in failover!"
    assert "store.mark_rate_limited" in content, \
        "mark_rate_limited not called in failover — rate limits not tracked!"


# ═══════════════════════════════════════════════════════════════════════
# 4. message-renderer.js: _isImageFile must declare 'ext' from filename
# ═══════════════════════════════════════════════════════════════════════

def test_message_renderer_no_undefined_ext() -> None:
    js = _read("web/static/modules/message-renderer.js")
    match = re.search(r'function\s+_isImageFile\s*\([^)]*\)\s*\{([^}]+)\}', js, re.DOTALL)
    assert match, "_isImageFile function not found in message-renderer.js!"
    body = match.group(1)
    assert ".split(" in body and ".pop()" in body, \
        "_isImageFile must derive 'ext' from the filename, not reference a global!"


# ═══════════════════════════════════════════════════════════════════════
# 5. app.js must call all critical initializations
# ═══════════════════════════════════════════════════════════════════════

REQUIRED_INITS = [
    "initSessionPage",
    "ChatForm.init",
    "startMessageHandler",
    "DebugPanel.bindDebugControls",
]


def test_app_js_has_all_initializations() -> None:
    app_js = _read("web/static/app.js")
    for init_name in REQUIRED_INITS:
        assert init_name in app_js, \
            f"Missing {init_name}() call in app.js — sessions/chat/skills won't work!"


# ═══════════════════════════════════════════════════════════════════════
# 6. app.js imports all required modules
# ═══════════════════════════════════════════════════════════════════════

REQUIRED_IMPORTS = [
    "session-page.js",
    "chat-form.js",
    "widgets/index.js",
    "debug-panel.js",
    "session-context.js",
    "asr/contract.js",
]


def test_app_js_imports_all_modules() -> None:
    app_js = _read("web/static/app.js")
    for mod in REQUIRED_IMPORTS:
        assert mod in app_js, \
            f"Missing import for {mod} in app.js!"
