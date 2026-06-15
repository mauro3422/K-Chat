"""Anti-regression tests for architectural and frontend bugs.

These tests exist to PREVENT the bugs we fixed today from coming back:
1. CSP missing blob: in img-src  → image paste previews blocked
2. Model discovery timeout in lifespan (get_verified_models without timeout)
3. Rate limit tracking integration
4. Undefined JS variable (`ext`) in message-renderer.js
5. Missing initialization calls in app.js (initSessionPage, ChatForm.init, etc.)
6. Missing imports in app.js

Widget-specific regressions covered:
7. CSP missing unsafe-inline in script-src → iframe srcdoc scripts blocked
8. buildIframeSrc escaping </script> → widget own scripts break
9. mountIframe called outside .then() scope → ReferenceError
10. Missing sandbox, resize script, or error handler → widget runtime broken

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


# ═══════════════════════════════════════════════════════════════════════
# 12. Entry points (web/, cli.py, gateway.py) must NOT import domain layers
#     directly. Domain = core, llm, tools, memory, context, skills.
#     They must go through src.api (the facade) instead.
# ═══════════════════════════════════════════════════════════════════════

_FORBIDDEN_DOMAIN = ("src.core", "src.llm", "src.tools", "src.memory", "src.context", "src.skills")
_IMPORT_RE = re.compile(r'^\s*(?:from\s+(src\.\w+)|import\s+(src\.\w+))\b')


async def test_web_never_imports_domain_directly() -> None:
    violations: list[str] = []
    for pyfile in sorted((PROJECT_ROOT / "web").rglob("*.py")):
        rel = pyfile.relative_to(PROJECT_ROOT)
        for lineno, line in enumerate(pyfile.read_text("utf-8").splitlines(), 1):
            m = _IMPORT_RE.match(line)
            if not m:
                continue
            mod = m.group(1) or m.group(2)
            if mod.startswith(_FORBIDDEN_DOMAIN):
                violations.append(f"  {rel}:{lineno}  {line.strip()}")
    assert not violations, \
        "web/ imports domain layer directly:\n" + "\n".join(violations)


async def test_cli_never_imports_domain_directly() -> None:
    content = _read("src/cli.py")
    violations: list[str] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        m = _IMPORT_RE.match(line)
        if not m:
            continue
        mod = m.group(1) or m.group(2)
        if mod.startswith(_FORBIDDEN_DOMAIN):
            violations.append(f"  src/cli.py:{lineno}  {line.strip()}")
    assert not violations, \
        "cli.py imports domain layer directly:\n" + "\n".join(violations)


async def test_gateway_never_imports_domain_directly() -> None:
    content = _read("src/gateway.py")
    violations: list[str] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        m = _IMPORT_RE.match(line)
        if not m:
            continue
        mod = m.group(1) or m.group(2)
        if mod.startswith(_FORBIDDEN_DOMAIN):
            violations.append(f"  src/gateway.py:{lineno}  {line.strip()}")
    assert not violations, \
        "gateway.py imports domain layer directly:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════════
# 13. No module-level singletons in src/ (must use DI)
# ═══════════════════════════════════════════════════════════════════════

_SINGLETON_RE = re.compile(
    r'^[a-zA-Z_]\w*\s*=\s*(?:load_config|ModelState|ProviderRegistry|ToolRegistry)\s*\('
)


async def test_no_module_level_singletons() -> None:
    violations: list[str] = []
    for pyfile in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        rel = pyfile.relative_to(PROJECT_ROOT)
        for lineno, line in enumerate(pyfile.read_text("utf-8").splitlines(), 1):
            if _SINGLETON_RE.match(line):
                violations.append(f"  {rel}:{lineno}  {line.strip()}")
    assert not violations, \
        "Module-level singletons found (violates DI rule):\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════════
# 14. src/api/__init__.py must export from all submodules
# ═══════════════════════════════════════════════════════════════════════

async def test_api_facade_exports_complete() -> None:
    content = _read("src/api/__init__.py")

    all_match = re.search(r'__all__\s*=\s*\[(.*?)\]', content, re.DOTALL)
    assert all_match, "src/api/__init__.py missing __all__"

    exports: set[str] = set(re.findall(r'"([^"]+)"', all_match.group(1)))
    assert len(exports) >= 30, \
        f"__all__ only has {len(exports)} exports, expected >= 30"

    required_imports = [
        "from src.api.session import",
        "from src.api.debug import",
        "from src.api.messages import",
        "from src.api.tools import",
        "from src.api.widgets import",
        "from src.api.orchestrator import",
        "from src.api.llm_client import",
        "from src.api.repos import",
        "from src.api.context import",
        "from src.api.background import",
        "from src.api.journal import",
        "from src.api.skills import",
        "from src.api.exceptions import",
    ]
    for imp in required_imports:
        assert imp in content, f"Missing import: '{imp}' in src/api/__init__.py"

    required_exports = [
        "ensure_session", "rename_session", "delete_session", "get_sessions",
        "save_debug_info", "get_debug_info", "append_asr_telemetry",
        "get_tool_history", "sanitize_widget_id",
        "save_widget_state", "get_widget_states",
        "db_save_widget", "db_get_widget",
        "chat_stream", "generate_session_id", "OrchestratorDeps",
        "get_default_model", "get_verified_models", "get_verified_models_safe",
        "get_repos", "init_db",
        "build_system_prompt",
        "auto_rename_session",
        "log_turn",
        "SkillRegistry",
        "ServiceException",
    ]
    missing = [e for e in required_exports if e not in exports]
    assert not missing, \
        f"Missing exports in src/api/__init__.__all__: {missing}"


# ═══════════════════════════════════════════════════════════════════════
# 15. CSP must include 'unsafe-inline' in script-src (widget iframe scripts)
# ═══════════════════════════════════════════════════════════════════════

async def test_csp_includes_unsafe_inline_for_script_src() -> None:
    content = _read("web/app_factory.py")
    assert "script-src 'self' 'unsafe-inline'" in content, \
        "CSP missing 'unsafe-inline' in script-src — widget iframe inline scripts blocked!"


# ═══════════════════════════════════════════════════════════════════════
# 16. buildIframeSrc must NOT escape </script> in widget code
#     Widget code goes in the HTML body; its own <script> tags must close
#     naturally. Escaping </script> → <\/script> breaks the widget's JS.
# ═══════════════════════════════════════════════════════════════════════

async def test_build_iframe_src_does_not_escape_closing_script() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    assert "code.replace" not in content or "/script" not in content[content.find("code.replace"):content.find("code.replace") + 100], \
        "buildIframeSrc escapes </script> in widget code — widget script blocks won't close!"
    # The widget code must be assigned directly, not transformed
    assert "var safeCode = code;" in content or "var safeCode=code;" in content, \
        "buildIframeSrc must use widget code as-is (no </script> escaping)!"


# ═══════════════════════════════════════════════════════════════════════
# 17. createIframe: mountIframe must only be called INSIDE the .then()
#     callback. Calling it outside (duplicate code) causes ReferenceError.
# ═══════════════════════════════════════════════════════════════════════

async def test_create_iframe_mount_iframe_only_in_then_scope() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    # Find the .then() callback opening
    then_start = content.find(".then(function(m)")
    assert then_start >= 0, "Missing .then() callback in createIframe!"
    
    # mountIframe must be defined INSIDE the .then() callback
    mount_def = content.find("function mountIframe(widgetCode)", then_start)
    assert mount_def >= 0, "mountIframe function not defined in .then() callback!"
    
    # Count mountIframe calls BEFORE the .then() opening — should be 0
    calls_before_then = content[:then_start].count("mountIframe(")
    # Count mountIframe calls AFTER the .then() opening — should be all of them
    calls_after_then = content[then_start:].count("mountIframe(")
    calls_total = content.count("mountIframe(")
    
    assert calls_before_then == 0, \
        f"mountIframe called {calls_before_then} time(s) BEFORE .then() scope — would be ReferenceError!"
    assert calls_after_then == calls_total, \
        f"mountIframe calls outside .then(): total={calls_total}, inside={calls_after_then}"
    assert calls_total >= 1, \
        "mountIframe never called — widget mounting broken!"


# ═══════════════════════════════════════════════════════════════════════
# 18. Iframe sandbox must include 'allow-scripts' (security baseline)
# ═══════════════════════════════════════════════════════════════════════

async def test_iframe_sandbox_has_allow_scripts() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    assert "iframe.sandbox = 'allow-scripts'" in content or 'iframe.sandbox="allow-scripts"' in content, \
        "Iframe missing sandbox='allow-scripts' — widget scripts won't execute!"
    assert "allow-same-origin" not in content, \
        "Iframe has allow-same-origin — sandbox bypass defeats widget isolation!"


# ═══════════════════════════════════════════════════════════════════════
# 19. buildIframeSrc must include auto-resize script (sendHeight, ResizeObserver)
# ═══════════════════════════════════════════════════════════════════════

async def test_build_iframe_src_has_resize_script() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    assert "sendHeight" in content, \
        "Missing sendHeight in iframe builder — widgets won't auto-resize!"
    assert "getDocHeight" in content, \
        "Missing getDocHeight in iframe builder — height measurement missing!"
    assert "ResizeObserver" in content, \
        "Missing ResizeObserver in iframe builder — dynamic resize won't work!"
    assert "resize-iframe" in content, \
        "Missing 'resize-iframe' postMessage — parent won't receive height updates!"


# ═══════════════════════════════════════════════════════════════════════
# 20. buildIframeSrc must handle null origin for postMessage (srcdoc iframes)
# ═══════════════════════════════════════════════════════════════════════

async def test_postmessage_handles_null_origin() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    assert 'window.location.origin==="null"?"*":' in content or 'window.location.origin==="null"?"*":' in content.replace(' ', ''), \
        "Missing null origin fallback in postMessage — messages from srcdoc iframes blocked!"


# ═══════════════════════════════════════════════════════════════════════
# 21. buildIframeSrc must include window.onerror for error reporting
# ═══════════════════════════════════════════════════════════════════════

async def test_iframe_has_error_handler() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    assert "window.onerror" in content, \
        "Missing window.onerror in iframe — widget errors silent!"
    assert "widget-error" in content, \
        "Missing 'widget-error' postMessage — errors not reported to parent!"


# ═══════════════════════════════════════════════════════════════════════
# 22. buildIframeSrc must expose saveState for widget state persistence
# ═══════════════════════════════════════════════════════════════════════

async def test_iframe_has_save_state() -> None:
    content = _read("web/static/modules/widgets/iframe-builder.js")
    assert "window.saveState" in content, \
        "Missing window.saveState in iframe — widget state can't be persisted!"
    assert "save-widget-state" in content, \
        "Missing 'save-widget-state' postMessage — widget state lost on reload!"


# ═══════════════════════════════════════════════════════════════════════
# 23. messaging.js must handle resize-iframe messages
# ═══════════════════════════════════════════════════════════════════════

async def test_messaging_handles_resize() -> None:
    content = _read("web/static/modules/widgets/messaging.js")
    assert 'event.data.type === "resize-iframe"' in content, \
        "Missing resize-iframe handler in messaging.js — iframe height won't update!"
    assert "iframe.style.height" in content, \
        "Missing iframe.style.height assignment — resize messages ignored!"


# ═══════════════════════════════════════════════════════════════════════
# 24. messaging.js must handle widget-error messages for debugging
# ═══════════════════════════════════════════════════════════════════════

async def test_messaging_handles_widget_error() -> None:
    content = _read("web/static/modules/widgets/messaging.js")
    assert 'event.data.type === "widget-error"' in content, \
        "Missing widget-error handler in messaging.js — widget errors invisible!"


# ═══════════════════════════════════════════════════════════════════════
# 25. core.js extract() must use the correct WIDGET_CONTAINER class
# ═══════════════════════════════════════════════════════════════════════

async def test_widget_extract_uses_correct_container_class() -> None:
    content = _read("web/static/modules/widgets/core.js")
    assert "C.WIDGET_CONTAINER" in content, \
        "Widget extraction must use dom-contracts C.WIDGET_CONTAINER — class mismatch!"
    assert "INLINE_WIDGET_BLOCK_RE" in content, \
        "Missing INLINE_WIDGET_BLOCK_RE regex — widget code blocks not detected!"
    assert "INLINE_WIDGET_TAG_RE" in content, \
        "Missing INLINE_WIDGET_TAG_RE regex — [Widget: key] tags not detected!"
