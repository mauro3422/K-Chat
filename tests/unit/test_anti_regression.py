"""Anti-regression tests for architectural and frontend bugs.

These tests exist to PREVENT the bugs we fixed today from coming back:
1. CSP missing blob: in img-src  â†’ image paste previews blocked
2. Model discovery timeout in lifespan (get_verified_models without timeout)
3. Rate limit tracking integration
4. Undefined JS variable (`ext`) in message-renderer.js
5. Missing initialization calls in app.js (initSessionPage, ChatForm.init, etc.)
6. Missing imports in app.js

Widget-specific regressions covered:
7. CSP missing unsafe-inline in script-src â†’ iframe srcdoc scripts blocked
8. buildIframeSrc escaping </script> â†’ widget own scripts break
9. mountIframe called outside .then() scope â†’ ReferenceError
10. Missing sandbox, resize script, or error handler â†’ widget runtime broken

These read the source files directly â€” no DB, no fixtures, no asyncio.

NOTE: All test functions are `async def` to work around the root conftest's
autouse=True async fixture (setup_test_db). The anyio marker is at module level.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
pytestmark = pytest.mark.anyio

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 1. CSP: blob: must be allowed in img-src
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_csp_includes_blob_for_img_src() -> None:
    content = _read("web/app_factory.py")
    assert "img-src 'self' data: blob:" in content, \
        "CSP missing blob: in img-src â€” blocked image paste previews!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 2. Lifespan: verified model priming must not await a sync function
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_lifespan_has_timeout_on_get_verified_models() -> None:
    content = _read("web/app_factory.py")
    assert "_prime_verified_model_cache(app)" in content, \
        "Missing verified-model priming in lifespan!"
    assert "get_verified_models(config=cfg)" in content, \
        "Zen-mode verified-model priming must pass the app config."
    assert "asyncio.wait_for(ensure_registry_refreshed(), timeout=timeout)" in content, \
        "Missing timeout on ensure_registry_refreshed in lifespan!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 3. Rate limit store integrated into failover
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_rate_limit_store_imported_in_failover() -> None:
    content = _read("src/llm/failover.py")
    assert "get_rate_limit_store" in content, \
        "Rate limit store not imported in failover!"
    assert "store.mark_rate_limited" in content, \
        "mark_rate_limited not called in failover â€” rate limits not tracked!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 4. message-renderer.js: _isImageFile must declare 'ext' from filename
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_message_renderer_uses_widget_registry_before_markdown() -> None:
    content = _read("web/src_ts/rendering/DomRenderer.ts")
    assert "widgetRegistry.extract(markdown)" in content, \
        "DomRenderer must extract widget markers before markdown parsing."
    assert "DOMPurify.sanitize" in content, \
        "DomRenderer must still sanitize rendered HTML."
    assert "data-widget-id" in content and "data-widget-key" in content, \
        "DomRenderer must allow widget metadata through sanitization."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 5. app.js must call all critical initializations
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

REQUIRED_INITS = [
    "new SystemLogPanel(apiClient)",
    "skillsUI.init()",
    "systemLogPanel.init()",
    "debug.init()",
    "chatForm.init()",
    "sessionList.init()",
    "sseClient.connect()",
]


async def test_app_ts_has_all_initializations() -> None:
    app_js = _read("web/src_ts/app.ts")
    for init_name in REQUIRED_INITS:
        assert init_name in app_js, \
            f"Missing {init_name} call in app.ts â€” TS bootstrap is incomplete!"


# 6. app.js must no longer import the legacy runtime modules
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_skills_ui_ts_exists() -> None:
    content = _read("web/src_ts/widgets/SkillsUI.ts")
    assert "export class SkillsUI" in content
    assert "init(): void" in content
    assert "fetchSkills()" in content


async def test_chat_form_ts_exists() -> None:
    content = _read("web/src_ts/core/ui/ChatForm.ts")
    assert "export class ChatForm" in content
    assert "handleSubmit()" in content
    assert "setStreamingState" in content


async def test_logger_ts_reexport_exists() -> None:
    content = _read("web/src_ts/core/infra/Logger.ts")
    assert "export class Logger" in content
    assert "sendClientLogs" in content
    assert "_flush" in content


async def test_api_client_ts_exposes_debug_and_asr_methods() -> None:
    content = _read("web/src_ts/api/ApiClient.ts")
    assert "sendClientLogs" in content
    assert "transcribeAudio" in content


async def test_session_store_ts_reexport_exists() -> None:
    content = _read("web/src_ts/core/session/SessionStore.ts")
    assert "export class SessionStore" in content
    assert "selectSession(id: string): Promise<void>" in content
    assert "loadSessions" in content


async def test_reasoning_handler_ts_exists() -> None:
    content = _read("web/src_ts/streaming/reasoning-handler.ts")
    assert "handleReasoning" in content
    assert "handleMemory" in content
    assert "details.open = true" in content


async def test_stream_error_handler_ts_exists() -> None:
    content = _read("web/src_ts/streaming/StreamErrorHandler.ts")
    assert "createStreamErrorHandler" in content
    assert "showRetryMessage" in content
    assert "error-retry-btn" in content or "rate-limit-card" in content


async def test_widget_container_renderer_ts_exists() -> None:
    content = _read("web/src_ts/rendering/WidgetContainerRenderer.ts")
    assert "processWidgetContainers" in content
    assert "C.WIDGET_CONTAINER" in content
    assert "widgetMatches" in content

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 7. pages.py must NOT hardcode model names (regression: ALL_GO sets)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_pages_no_hardcoded_model_sets() -> None:
    content = _read("web/routers/pages.py")
    # GO_PREMIUM/GO_STANDARD/GO_ECONOMY should NOT exist as hardcoded sets
    assert "GO_PREMIUM" not in content or "{" not in content.split("GO_PREMIUM")[1][:50], \
        "GO_PREMIUM hardcoded set found in pages.py â€” regression! Must use ModelRegistry."
    assert "GO_STANDARD" not in content or "{" not in content.split("GO_STANDARD")[1][:50], \
        "GO_STANDARD hardcoded set found in pages.py â€” regression! Must use ModelRegistry."
    assert "GO_ECONOMY" not in content or "{" not in content.split("GO_ECONOMY")[1][:50], \
        "GO_ECONOMY hardcoded set found in pages.py â€” regression! Must use ModelRegistry."
    assert "ALL_GO" not in content or "{" not in content.split("ALL_GO")[1][:50], \
        "ALL_GO hardcoded set found in pages.py â€” regression! Must use ModelRegistry."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 8. model_registry.py: _infer_tier must use patterns, not hardcoded names
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_infer_tier_uses_patterns_not_names() -> None:
    content = _read("src/llm/model_registry.py")
    # Must use _PREMIUM_PATTERNS / _STANDARD_PATTERNS, not hardcoded model IDs
    assert "_PREMIUM_PATTERNS" in content, \
        "Missing _PREMIUM_PATTERNS â€” regression to hardcoded model names!"
    assert "_STANDARD_PATTERNS" in content, \
        "Missing _STANDARD_PATTERNS â€” regression to hardcoded model names!"
    # Should NOT contain any specific model ID as a string literal in _infer_tier
    infer_section = content[content.find("def _infer_tier"):content.find("def _infer_tier") + 2000]
    for hardcoded in ["deepseek-v4", "minimax-m3", "qwen3.7", "glm-5", "kimi-k2"]:
        assert hardcoded not in infer_section, \
            f"Hardcoded model name '{hardcoded}' found in _infer_tier â€” must use patterns!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 9. ModelRegistry must exist and have the required methods
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
            f"Missing '{method}' in ModelRegistry â€” required for dynamic discovery!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 10. Go quota detection must be integrated in failover
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

# ═══════════════════════════════════════════════════════════════════════════════
# 10. memory.analysis must stay lightweight at package import time
# ═══════════════════════════════════════════════════════════════════════════════

async def test_memory_analysis_package_is_lazy_and_does_not_reexport_heavy_modules() -> None:
    content = _read("src/memory/analysis/__init__.py")
    assert "__all__: list[str] = []" in content

    for name in [key for key in sys.modules if key == "src.memory.analysis" or key.startswith("src.memory.analysis.")]:
        sys.modules.pop(name, None)

    import src.memory.analysis as analysis

    assert analysis.__all__ == []
    assert not hasattr(analysis, "CombinedScorer")
    assert not hasattr(analysis, "MemoryCorpus")
    assert "src.memory.analysis.scoring" not in sys.modules
    assert "src.memory.analysis.corpus" not in sys.modules
    assert "src.memory.analysis.graph_analysis" not in sys.modules

    from src.memory.analysis.scoring import compute_statistical_thresholds

    assert callable(compute_statistical_thresholds)
    assert "src.memory.analysis.scoring" in sys.modules


async def test_go_quota_detected_in_failover() -> None:
    content = _read("src/llm/failover.py")
    assert "insufficient balance" in content, \
        "Missing 'insufficient balance' detection in failover â€” Go quota not tracked!"
    assert "mark_quota_exhausted" in content, \
        "Missing mark_quota_exhausted call in failover â€” Go quota not reported!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 11. /models/availability must return go_quota_exhausted
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_availability_endpoint_includes_quota() -> None:
    content = _read("web/routers/debug.py")
    assert "go_quota_exhausted" in content, \
        "Missing go_quota_exhausted in /models/availability â€” Go quota not exposed to UI!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 12. Entry points (web/, cli.py, gateway.py) must NOT import domain layers
#     directly. Domain = core, llm, tools, memory, context, skills.
#     They must go through src.api (the facade) instead.
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

_FORBIDDEN_DOMAIN = ("src.core", "src.llm", "src.tools", "src.memory", "src.context", "src.skills")
_IMPORT_RE = re.compile(r'^\s*(?:from\s+(src\.\w+)|import\s+(src\.\w+))\b')


async def test_web_never_imports_domain_directly() -> None:
    violations: list[str] = []
    for pyfile in sorted((PROJECT_ROOT / "web").rglob("*.py")):
        rel = pyfile.relative_to(PROJECT_ROOT)
        # app_factory.py is the composition root — it's the one place where
        # cross-layer wiring is intentional and necessary.
        if rel.name == "app_factory.py":
            continue
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 13. No module-level singletons in src/ (must use DI)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 14. src/api/__init__.py must stay a minimal compatibility shim
# -----------------------------------------------------------------------

async def test_api_facade_is_minimal_shim() -> None:
    content = _read("src/api/__init__.py")
    assert "Compatibilidad mínima" in content
    assert "from src.api.repos import get_repos" not in content
    assert "def __getattr__(" in content
    assert "from src.api.session import" not in content


# 15. CSP must include 'unsafe-inline' in script-src (widget iframe scripts)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_csp_includes_unsafe_inline_for_script_src() -> None:
    content = _read("web/app_factory.py")
    assert "script-src 'self' 'unsafe-inline'" in content, \
        "CSP missing 'unsafe-inline' in script-src â€” widget iframe inline scripts blocked!"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 16. buildIframeSrc must NOT escape </script> in widget code
#     Widget code goes in the HTML body; its own <script> tags must close
#     naturally. Escaping </script> â†’ <\/script> breaks the widget's JS.
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_sanitizes_widget_code() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "const safeCode = this.sanitizeWidgetCode(code)" in content, \
        "IframeBuilder must sanitize widget code before embedding it."
    assert ".replace(/<animate\\b" in content and ".replace(/<set\\b" in content, \
        "IframeBuilder must strip SVG animation tags that trigger feedback loops."
    assert "stateStr = (initialState" in content and "replace(/<\\/script/gi" in content, \
        "IframeBuilder must only escape closing script tags in the serialized state."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 17. createIframe: mountIframe must only be called INSIDE the .then()
#     callback. Calling it outside (duplicate code) causes ReferenceError.
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_mounts_sandboxed_iframe() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "const mountIframe = (widgetCode: string)" in content, \
        "IframeBuilder must keep iframe mounting inside the widget creation flow."
    assert "iframe.setAttribute('sandbox', 'allow-scripts allow-modals')" in content, \
        "IframeBuilder must sandbox widget iframes with script execution enabled."
    assert "iframe.srcdoc = this.buildSrcDoc(id, widgetCode, parsedState);" in content, \
        "IframeBuilder must keep widget HTML in srcdoc."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 18. Iframe sandbox must include 'allow-scripts' (security baseline)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_handles_widget_postmessage_contract() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "window.saveState" in content
    assert "resize-iframe" in content
    assert "window.onerror" in content
    assert "widget-error" in content
    assert "if (event.origin !== 'null') return;" in content, \
        "IframeBuilder must only accept messages from srcdoc/null-origin iframes."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 19. buildIframeSrc must include auto-resize script (sendHeight, ResizeObserver)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_has_resize_script() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "sendHeight" in content, \
        "IframeBuilder must keep the resize bridge alive."
    assert "getDocHeight" in content, \
        "IframeBuilder must measure height from the live document body."
    assert "ResizeObserver" in content, \
        "IframeBuilder must debounce dynamic resize updates."
    assert "resize-iframe" in content, \
        "IframeBuilder must notify the parent when iframe height changes."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 20. buildIframeSrc must handle null origin for postMessage (srcdoc iframes)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_has_null_origin_guard() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "if (event.origin !== 'null') return;" in content, \
        "IframeBuilder must reject postMessage events from non-srcdoc origins."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 21. buildIframeSrc must include window.onerror for error reporting
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_has_error_handler() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "window.onerror" in content, \
        "IframeBuilder must surface widget errors."
    assert "widget-error" in content, \
        "IframeBuilder must report widget errors to the parent."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 22. buildIframeSrc must expose saveState for widget state persistence
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_iframe_builder_has_save_state() -> None:
    content = _read("web/src_ts/rendering/IframeBuilder.ts")
    assert "window.saveState" in content, \
        "IframeBuilder must expose saveState for widget persistence."
    assert "save-widget-state" in content, \
        "IframeBuilder must post widget state changes back to the host."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 23. messaging.js must handle resize-iframe messages
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_content_handler_keeps_widget_pipeline_intact() -> None:
    content = _read("web/src_ts/streaming/ContentHandler.ts")
    assert "ensureWidgetContainers" in content
    assert "renderTextSegments" in content
    assert "processWidgetContainers" in content


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 24. messaging.js must handle widget-error messages for debugging
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_content_handler_keeps_error_renderer_wired() -> None:
    content = _read("web/src_ts/streaming/ContentHandler.ts")
    assert "ErrorRenderer" in content
    assert "handleError" in content


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 25. core.js extract() must use the correct WIDGET_CONTAINER class
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

async def test_widget_container_renderer_uses_real_dom_contract() -> None:
    content = _read("web/src_ts/rendering/WidgetContainerRenderer.ts")
    assert "C.WIDGET_CONTAINER" in content, \
        "WidgetContainerRenderer must use the shared DOM contract class."
    assert "processWidgetContainers" in content, \
        "WidgetContainerRenderer must remain the source of widget extraction."
    assert "widgetMatches" in content, \
        "WidgetContainerRenderer must preserve widget detection results."


# ─────────────────────────────────────────────────────────────────────────────
# 26. Venv / Python environment health
#     Prevents the constant "ModuleNotFoundError: No module named 'fastembed'"
#     that happens when tests run with system python3 instead of the project's
#     venv. If this test fails, run: scripts/test.sh ...
# ─────────────────────────────────────────────────────────────────────────────

async def test_fastembed_is_importable() -> None:
    """fastembed must be importable — proves we're inside the project venv."""
    import fastembed  # noqa: F401
    assert fastembed.__file__ is not None, \
        "fastembed not importable! You're probably running tests with system " \
        "python3 instead of venv/bin/python. Use: scripts/test.sh"


async def test_project_venv_has_python_and_venv_bin_python() -> None:
    """venv/bin/python must exist and be executable."""
    venv_root = PROJECT_ROOT / "venv"
    if os.name == "nt" and not venv_root.exists():
        assert Path(sys.executable).exists()
        return
    venv_python = (
        venv_root / "Scripts" / "python.exe"
        if os.name == "nt"
        else venv_root / "bin" / "python"
    )
    assert venv_python.exists(), \
        f"venv/bin/python not found at {venv_python} — venv may be missing or broken"
    assert os.access(str(venv_python), os.X_OK), \
        f"venv/bin/python at {venv_python} is not executable"


async def test_project_venv_has_fastembed_wheel() -> None:
    """The project venv must have fastembed installed."""
    venv_root = PROJECT_ROOT / "venv"
    if os.name == "nt" and not venv_root.exists():
        import fastembed

        assert fastembed.__file__ is not None
        return
    if os.name == "nt":
        matched = list((venv_root / "Lib" / "site-packages").glob("fastembed"))
    else:
        matched = list((venv_root / "lib").glob("python*/site-packages/fastembed"))
    assert matched, \
        "fastembed not found in venv/lib/.../site-packages — run: " \
        "venv/bin/pip install -r requirements.txt"


async def test_dot_venv_symlink_is_valid() -> None:
    """.venv must either not exist, or be a valid symlink pointing to venv/.

    A broken .venv symlink causes scripts/kairos-node.sh and other tools
    that reference .venv/bin/pip to silently fall back to system python3,
    which lacks fastembed and other project dependencies.
    """
    dot_venv = PROJECT_ROOT / ".venv"
    if not dot_venv.exists():
        return  # .venv is optional
    if dot_venv.is_symlink():
        target = dot_venv.resolve()
        assert target.name == "venv" or target == PROJECT_ROOT / "venv", \
            f".venv symlink points to {target}, expected venv/"
    # If it's a real directory, that's also fine (some setups create a full venv)


async def test_active_python_prefix_is_not_system() -> None:
    """The running Python interpreter must not be the system python.

    If sys.prefix is '/' or '/usr', the tests are running on system python
    which lacks project dependencies (fastembed, etc.). Use scripts/test.sh.
    """
    import sys
    assert sys.prefix not in ("/", "/usr", "/usr/local"), \
        f"Running on system python (prefix={sys.prefix}) — fastembed and other " \
        "project deps are missing! Use: scripts/test.sh"


async def test_scripts_test_sh_exists_and_uses_venv() -> None:
    """scripts/test.sh must exist and reference venv/bin/python."""
    test_sh = PROJECT_ROOT / "scripts" / "test.sh"
    assert test_sh.exists(), \
        "scripts/test.sh missing — this is the canonical way to run tests " \
        "with the project venv (which has fastembed, pytest-testmon, etc.)"
    content = test_sh.read_text("utf-8")
    assert "venv/bin/python" in content, \
        "scripts/test.sh must check venv/bin/python first to avoid falling " \
        "back to system python3 which lacks fastembed."


# ─────────────────────────────────────────────────────────────────────────────
# 27. TOCTOU race condition fixes (2026-07-03)
#     Prevents the ERR_CONNECTION_REFUSED crash caused by concurrent requests
#     hitting UNIQUE constraint on sessions.session_id, and similar patterns.
# ─────────────────────────────────────────────────────────────────────────────

async def test_session_ensure_uses_insert_or_ignore() -> None:
    """session_repository.py ensure() must use INSERT OR IGNORE, not SELECT+INSERT."""
    content = _read("src/memory/repos/session_repository.py")
    assert "INSERT OR IGNORE INTO sessions" in content, \
        "session_repository.py ensure() must use INSERT OR IGNORE (atomic)."
    # The ensure() method should NOT have a SELECT followed by INSERT.
    # Find the ensure() method body and check.
    ensure_start = content.find("async def ensure(")
    ensure_end = content.find("async def exists(", ensure_start)
    ensure_body = content[ensure_start:ensure_end]
    assert "SELECT 1 FROM sessions" not in ensure_body, \
        "ensure() must NOT use SELECT before INSERT — TOCTOU race condition."


async def test_work_catalog_mark_uses_on_conflict_do_update() -> None:
    """work_catalog_repo.py mark() must use INSERT ... ON CONFLICT DO UPDATE."""
    content = _read("src/memory/repos_memory/work_catalog_repo.py")
    assert "ON CONFLICT (source, source_key, item_idx" in content, \
        "work_catalog_repo.py must use ON CONFLICT DO UPDATE (atomic upsert)."
    assert "result.rowcount == 0" not in content, \
        "work_catalog_repo.py must NOT use UPDATE-then-INSERT pattern — TOCTOU bug."


async def test_vector_store_insert_has_atomic_dedup() -> None:
    """VectorStore.insert() must check content_hash atomically inside _lock."""
    content = _read("src/memory/vector/store.py")
    assert "SELECT rowid FROM vec_meta WHERE content_hash = ? LIMIT 1" in content, \
        "VectorStore.insert() missing atomic dedup check — duplicate vectors possible."
    assert "if content_hash:" in content, \
        "VectorStore must dedup by content_hash to prevent duplicate embeddings."


async def test_curate_has_pre_mark_processing() -> None:
    """curate.py must pre-mark as 'processing' before LLM call to prevent dupes."""
    content = _read("src/memory/curator/curate.py")
    assert 'status="processing"' in content, \
        "curate.py must pre-mark clusters/sessions as 'processing' before LLM call " \
        "to prevent duplicate LLM work from concurrent curators."
    assert "Pre-mark as" in content, \
        "curate.py must have comment explaining the pre-mark TOCTOU fix."


async def test_curate_retire_uses_per_session_commit() -> None:
    """_retire_old_sessions() must commit per session, not all at once."""
    content = _read("src/memory/curator/curate.py")
    assert "del_conn.commit()" in content, \
        "curate.py _retire_old_sessions must commit deleted_sessions per session."
    assert "conn.rollback()" in content, \
        "curate.py _retire_old_sessions must rollback on session deletion failure."


async def test_watchdog_has_grace_300_and_failures_6() -> None:
    """Watchdog must tolerate slow model warmup (300s grace, 6 failures)."""
    content = _read(".kairos/watchdog.py")
    assert 'STARTUP_GRACE = int(os.getenv("WATCHDOG_STARTUP_GRACE", "300"))' in content, \
        "Watchdog STARTUP_GRACE must be 300s to tolerate model warmup."
    assert 'REQUIRED_FAILURES = int(os.getenv("WATCHDOG_REQUIRED_FAILURES", "6"))' in content, \
        "Watchdog REQUIRED_FAILURES must be 6 (was 3) to avoid false positives."
    assert "_managed_service_is_active() and downtime < STARTUP_GRACE" in content, \
        "Active services inside startup grace must not be restarted."


async def test_watchdog_delegates_web_process_ownership_to_systemd() -> None:
    """The watchdog must never create a second uvicorn process."""
    content = _read(".kairos/watchdog.py")
    unit = _read(".kairos/k-chat-watchdog.service")

    assert "subprocess.Popen" not in content
    assert '["systemctl", "--user", "restart", service]' in content
    assert "Watchdog exited; managed web service left untouched" in content
    assert "Wants=network-online.target k-chat.service" in unit
    assert "Environment=KAIROS_WEB_SERVICE=k-chat.service" in unit


async def test_models_availability_auto_refreshes_when_empty() -> None:
    """debug.py /models/availability must auto-refresh when registry is empty."""
    content = _read("web/routers/debug.py")
    assert 'reg.summary()["total_models"] == 0' in content, \
        "debug.py must auto-refresh model registry when empty (lazy recovery)."
    assert "ensure_registry_refreshed()" in content, \
        "debug.py must call ensure_registry_refreshed() on empty registry."


async def test_ml_preload_runs_as_create_task() -> None:
    """ML model preload must run as asyncio.create_task, not blocking lifespan."""
    content = _read("web/app_factory.py")
    assert "async def _warmup_ml_models" in content, \
        "app_factory.py must define _warmup_ml_models as background coroutine."
    assert "asyncio.create_task(_warmup_ml_models())" in content, \
        "app_factory.py must run ML warmup as background task, not blocking startup."
    assert 'getattr(cfg, "node_role", "")' in content, \
        "Secondary nodes must be able to skip resource-heavy ML preload."
    assert "await asyncio.to_thread(reranker._load_model)" in content, \
        "Reranker preload must not block the event loop."
    # Preload must NOT block the yield (i.e., no await before yield)
    warmup_pos = content.find("_warmup_ml_models")
    yield_pos = content.find("yield")
    assert warmup_pos > yield_pos or warmup_pos == -1, \
        "ML preload must run AFTER yield or as background task, not blocking startup."


async def test_lifespan_model_prime_runs_as_create_task() -> None:
    """Model registry priming must run as background task."""
    content = _read("web/app_factory.py")
    assert "asyncio.create_task(_prime_model_registry())" in content, \
        "Model registry priming must run as background task (not blocking lifespan)."

# ─────────────────────────────────────────────────────────────────────────────
# 28. RetryController cancels pending retry on abort (2026-07-03)
#     resetRetryCount() must clear any pending setTimeout for scheduled retries.
#     Without this, aborted streams would auto-retry after the timeout fires.
# ─────────────────────────────────────────────────────────────────────────────

async def test_retry_controller_has_retry_timer_field() -> None:
    """RetryHandler.ts must have _retryTimer field to track scheduled retries."""
    content = _read("web/src_ts/core/ui/RetryHandler.ts")
    assert "_retryTimer" in content, \
        "RetryHandler.ts missing _retryTimer field — cannot cancel pending retries."


async def test_retry_controller_has_cancel_pending_retry() -> None:
    """RetryHandler.ts must have _cancelPendingRetry() to cancel scheduled retries."""
    content = _read("web/src_ts/core/ui/RetryHandler.ts")
    assert "_cancelPendingRetry" in content, \
        "RetryHandler.ts missing _cancelPendingRetry() method — retries fire after abort."


async def test_retry_controller_calls_clear_timeout() -> None:
    """RetryHandler.ts must call clearTimeout to cancel pending retry timers."""
    content = _read("web/src_ts/core/ui/RetryHandler.ts")
    assert "clearTimeout" in content, \
        "RetryHandler.ts missing clearTimeout call — _cancelPendingRetry is a no-op."


# ─────────────────────────────────────────────────────────────────────────────
# 29. Model selector sends empty string, not 'default' (2026-07-03)
#     Backend uses get_default_model() when model is falsy. Sending 'default'
#     as a literal string bypasses that logic and selects a possibly invalid model.
# ─────────────────────────────────────────────────────────────────────────────

async def test_ndjson_client_no_default_model_fallback() -> None:
    """NDJSONStreamClient.ts must NOT use 'default' as a fallback model string."""
    content = _read("web/src_ts/streaming/NDJSONStreamClient.ts")
    assert "'default'" not in content, \
        "NDJSONStreamClient.ts uses 'default' as fallback model — backend " \
        "get_default_model() is bypassed!"


async def test_stream_orchestrator_no_default_model_fallback() -> None:
    """StreamOrchestrator.ts must NOT use 'default' as a fallback model string."""
    content = _read("web/src_ts/streaming/StreamOrchestrator.ts")
    assert "'default'" not in content, \
        "StreamOrchestrator.ts uses 'default' as fallback model — backend " \
        "get_default_model() is bypassed!"


# ─────────────────────────────────────────────────────────────────────────────
# 30. Error messages wrapped in String() (2026-07-03)
#     Without String(), non-string error values (objects) render as
#     "[object Object]" in the UI, making error messages useless.
# ─────────────────────────────────────────────────────────────────────────────

async def test_stream_orchestrator_wraps_error_in_string() -> None:
    """StreamOrchestrator.ts must wrap parsed.message in String()."""
    content = _read("web/src_ts/streaming/StreamOrchestrator.ts")
    assert "String(parsed.message" in content, \
        "StreamOrchestrator.ts missing String(parsed.message) — error objects " \
        "render as '[object Object]' in the UI!"


# ─────────────────────────────────────────────────────────────────────────────
# 31. DomTreeSerializer uses getAttribute('class') for SVG compatibility
#     e.className returns SVGAnimatedString for SVG elements (not a plain string).
#     getAttribute('class') always returns a string, supporting both HTML and SVG.
# ─────────────────────────────────────────────────────────────────────────────

async def test_dom_tree_serializer_uses_get_attribute_class() -> None:
    """DomTreeSerializer.ts must use getAttribute('class'), not e.className."""
    content = _read("web/src_ts/core/debug/DomTreeSerializer.ts")
    assert "getAttribute('class')" in content, \
        "DomTreeSerializer.ts missing getAttribute('class') — SVG elements break!"
    assert "e.className" not in content, \
        "DomTreeSerializer.ts uses e.className — SVGAnimatedString breaks debug panel!"


# ─────────────────────────────────────────────────────────────────────────────
# 32. Debug panel refresh interval increased from 400ms to 3000ms (2026-07-03)
#     400ms is too aggressive — it keeps the Connection Pool full and wastes CPU.
#     3000ms is a reasonable balance between responsiveness and resource usage.
# ─────────────────────────────────────────────────────────────────────────────

async def test_debug_refresh_interval_is_reasonable() -> None:
    """app.ts debug refresh interval must be >=2000ms, not 400ms."""
    content = _read("web/src_ts/app.ts")
    # Find the debug setInterval call and the next setInterval call
    debug_start = content.find("const debugIntervalId = setInterval")
    next_interval = content.find("const lanStatusIntervalId = setInterval", debug_start)
    debug_section = content[debug_start:next_interval]
    assert ", 400)" not in debug_section, \
        "app.ts debug refresh interval is 400ms — regression to aggressive polling!"
    assert "}, 3000)" in debug_section, \
        "app.ts debug refresh interval is NOT 3000ms — changed or regressed!"


# ─────────────────────────────────────────────────────────────────────────────
# 33. Scroll restoration uses requestAnimationFrame in DebugManager (2026-07-03)
#     Synchronous scrollTop assignment before the browser has re-laid-out the
#     DOM causes scroll positions to be lost. requestAnimationFrame ensures the
#     browser has completed layout before we restore scroll positions.
# ─────────────────────────────────────────────────────────────────────────────

async def test_debug_manager_scroll_restoration_uses_raf() -> None:
    """DebugManager.ts must use requestAnimationFrame before restoring scrollTop."""
    content = _read("web/src_ts/core/debug/DebugManager.ts")
    # Find the scroll restoration block (after "Restore scroll positions")
    restore_start = content.find("// Restore scroll positions")
    restore_section = content[restore_start:restore_start + 500]
    assert "requestAnimationFrame" in restore_section, \
        "DebugManager.ts scroll restoration missing requestAnimationFrame — " \
        "scroll positions lost after layout!"
    assert "scrollTop" in restore_section, \
        "DebugManager.ts scroll restoration missing scrollTop assignment."


# ─────────────────────────────────────────────────────────────────────────────
# 34. Copy handler handles text node targets (2026-07-03)
#     When clicking on an emoji or text inside a button, e.target is a Text node.
#     closest() only exists on Element, so calling it on a Text node would throw.
# ─────────────────────────────────────────────────────────────────────────────

async def test_debug_manager_copy_handles_text_nodes() -> None:
    """DebugManager.ts handleCopyClick must check for Node.TEXT_NODE."""
    content = _read("web/src_ts/core/debug/DebugManager.ts")
    assert "Node.TEXT_NODE" in content, \
        "DebugManager.ts missing Node.TEXT_NODE check — copy button breaks " \
        "when clicking on emoji or inline text!"


# ─────────────────────────────────────────────────────────────────────────────
# 35. Copy has execCommand fallback for non-HTTPS (2026-07-03)
#     navigator.clipboard.writeText() requires a secure context (HTTPS or
#     localhost). On non-secure contexts, execCommand('copy') is the fallback.
# ─────────────────────────────────────────────────────────────────────────────

async def test_debug_manager_copy_has_exec_command_fallback() -> None:
    """DebugManager.ts copyText must have execCommand('copy') fallback."""
    content = _read("web/src_ts/core/debug/DebugManager.ts")
    assert "execCommand" in content, \
        "DebugManager.ts missing execCommand fallback — clipboard copy fails " \
        "on non-HTTPS connections!"


# ─────────────────────────────────────────────────────────────────────────────
# 36. handleCopyClick handles all-session copy action (2026-07-03)
#     The "Copy" button in the Session Data section uses data-copy-action="all-session".
#     Without this handler, clicking it does nothing silently.
# ─────────────────────────────────────────────────────────────────────────────

async def test_debug_manager_handle_copy_click_all_session() -> None:
    """DebugManager.ts handleCopyClick must handle 'all-session' action."""
    content = _read("web/src_ts/core/debug/DebugManager.ts")
    assert "all-session" in content, \
        "DebugManager.ts missing 'all-session' copy action — Session Data " \
        "copy button is a dead click!"


# ─────────────────────────────────────────────────────────────────────────────
# 37. handleCopyClick has else clause for unhandled actions (2026-07-03)
#     Unknown data-copy-action values should log a warning instead of failing
#     silently. This makes debugging new copy buttons easier.
# ─────────────────────────────────────────────────────────────────────────────

async def test_debug_manager_handle_copy_click_has_else_clause() -> None:
    """DebugManager.ts handleCopyClick must have else clause for unhandled actions."""
    content = _read("web/src_ts/core/debug/DebugManager.ts")
    assert "unhandled copy action" in content, \
        "DebugManager.ts missing 'unhandled copy action' else clause — " \
        "unknown copy actions fail silently!"
