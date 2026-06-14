"""Anti-regression tests for architectural and frontend bugs.

These tests exist to PREVENT the bugs we fixed today from coming back:
1. CSP missing blob: in img-src  → image paste previews blocked
2. Model discovery timeout in lifespan (get_verified_models without timeout)
3. Rate limit tracking integration
4. Undefined JS variable (`ext`) in message-renderer.js
5. Missing initialization calls in app.js (initSessionPage, ChatForm.init, etc.)
6. Missing imports in app.js

These read the source files directly — no DB, no fixtures, no asyncio.

NOTE: All test functions are `async def` to work around the root conftest's
autouse=True async fixture (setup_test_db). The anyio marker is at module level.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
pytestmark = pytest.mark.anyio

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# 1. CSP: blob: must be allowed in img-src
# ═══════════════════════════════════════════════════════════════════════

async def test_csp_includes_blob_for_img_src() -> None:
    content = _read("web/app_factory.py")
    assert "img-src 'self' data: blob:" in content, \
        "CSP missing blob: in img-src — blocked image paste previews!"


# ═══════════════════════════════════════════════════════════════════════
# 2. Lifespan: get_verified_models must have timeout
# ═══════════════════════════════════════════════════════════════════════

async def test_lifespan_has_timeout_on_get_verified_models() -> None:
    content = _read("web/app_factory.py")
    assert "asyncio.wait_for(get_verified_models(), timeout=10)" in content, \
        "Missing timeout on get_verified_models in lifespan — server startup hangs!"
    assert "asyncio.TimeoutError" in content, \
        "Missing TimeoutError handler in lifespan!"


# ═══════════════════════════════════════════════════════════════════════
# 3. Rate limit store integrated into failover
# ═══════════════════════════════════════════════════════════════════════

async def test_rate_limit_store_imported_in_failover() -> None:
    content = _read("src/llm/failover.py")
    assert "get_rate_limit_store" in content, \
        "Rate limit store not imported in failover!"
    assert "store.mark_rate_limited" in content, \
        "mark_rate_limited not called in failover — rate limits not tracked!"


# ═══════════════════════════════════════════════════════════════════════
# 4. message-renderer.js: _isImageFile must declare 'ext' from filename
# ═══════════════════════════════════════════════════════════════════════

async def test_message_renderer_no_undefined_ext() -> None:
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


async def test_app_js_has_all_initializations() -> None:
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


async def test_app_js_imports_all_modules() -> None:
    app_js = _read("web/static/app.js")
    for mod in REQUIRED_IMPORTS:
        assert mod in app_js, \
            f"Missing import for {mod} in app.js!"


# ═══════════════════════════════════════════════════════════════════════
# 7. pages.py must NOT hardcode model names (regression: ALL_GO sets)
# ═══════════════════════════════════════════════════════════════════════

async def test_pages_no_hardcoded_model_sets() -> None:
    content = _read("web/routers/pages.py")
    # GO_PREMIUM/GO_STANDARD/GO_ECONOMY should NOT exist as hardcoded sets
    assert "GO_PREMIUM" not in content or "{" not in content.split("GO_PREMIUM")[1][:50], \
        "GO_PREMIUM hardcoded set found in pages.py — regression! Must use ModelRegistry."
    assert "GO_STANDARD" not in content or "{" not in content.split("GO_STANDARD")[1][:50], \
        "GO_STANDARD hardcoded set found in pages.py — regression! Must use ModelRegistry."
    assert "GO_ECONOMY" not in content or "{" not in content.split("GO_ECONOMY")[1][:50], \
        "GO_ECONOMY hardcoded set found in pages.py — regression! Must use ModelRegistry."
    assert "ALL_GO" not in content or "{" not in content.split("ALL_GO")[1][:50], \
        "ALL_GO hardcoded set found in pages.py — regression! Must use ModelRegistry."


# ═══════════════════════════════════════════════════════════════════════
# 8. model_registry.py: _infer_tier must use patterns, not hardcoded names
# ═══════════════════════════════════════════════════════════════════════

async def test_infer_tier_uses_patterns_not_names() -> None:
    content = _read("src/llm/model_registry.py")
    # Must use _PREMIUM_PATTERNS / _STANDARD_PATTERNS, not hardcoded model IDs
    assert "_PREMIUM_PATTERNS" in content, \
        "Missing _PREMIUM_PATTERNS — regression to hardcoded model names!"
    assert "_STANDARD_PATTERNS" in content, \
        "Missing _STANDARD_PATTERNS — regression to hardcoded model names!"
    # Should NOT contain any specific model ID as a string literal in _infer_tier
    infer_section = content[content.find("def _infer_tier"):content.find("def _infer_tier") + 2000]
    for hardcoded in ["deepseek-v4", "minimax-m3", "qwen3.7", "glm-5", "kimi-k2"]:
        assert hardcoded not in infer_section, \
            f"Hardcoded model name '{hardcoded}' found in _infer_tier — must use patterns!"


# ═══════════════════════════════════════════════════════════════════════
# 9. ModelRegistry must exist and have the required methods
# ═══════════════════════════════════════════════════════════════════════

async def test_model_registry_has_required_api() -> None:
    content = _read("src/llm/model_registry.py")
    required = [
        "class ModelRegistry",
        "async def refresh",
        "def get_tier",
        "def get_go_models",
        "def get_free_candidates",
        "def get_all_models",
        "def mark_quota_exhausted",
        "def is_quota_exhausted",
        "def summary",
        "_PREMIUM_PATTERNS",
        "_STANDARD_PATTERNS",
    ]
    for method in required:
        assert method in content, \
            f"Missing '{method}' in ModelRegistry — required for dynamic discovery!"


# ═══════════════════════════════════════════════════════════════════════
# 10. Go quota detection must be integrated in failover
# ═══════════════════════════════════════════════════════════════════════

async def test_go_quota_detected_in_failover() -> None:
    content = _read("src/llm/failover.py")
    assert "insufficient balance" in content, \
        "Missing 'insufficient balance' detection in failover — Go quota not tracked!"
    assert "mark_quota_exhausted" in content, \
        "Missing mark_quota_exhausted call in failover — Go quota not reported!"


# ═══════════════════════════════════════════════════════════════════════
# 11. /models/availability must return go_quota_exhausted
# ═══════════════════════════════════════════════════════════════════════

async def test_availability_endpoint_includes_quota() -> None:
    content = _read("web/routers/debug.py")
    assert "go_quota_exhausted" in content, \
        "Missing go_quota_exhausted in /models/availability — Go quota not exposed to UI!"
