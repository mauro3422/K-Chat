# Changelog

> **Regla**: Este archivo es solo el índice. El detalle de cada versión está en `changelogs/vX.Y.Z.md`.
> Cada nueva versión DEBE crear su archivo correspondiente en `changelogs/` y agregarse aquí.
> Las entradas describen el estado del proyecto en el momento de cada release.

## [v0.0.54] — 2026-06-13 — [Detalle](changelogs/v0.0.54.md)
- **Lego hardening**: runtime sin wrappers viejos, historial tipado con `HistoryMessage`, sesión/memoria con contratos explícitos
- **Contexto**: `load_context()` quedó pura; `TOOLS.md` se genera fuera del flujo de lectura
- **Web/frontend**: routers y servicios usan imports directos; transiciones legacy quedaron acotadas, `session-page.js` dejó de reconstruir acciones con `innerHTML`, `debug-panel.js` dejó de pintar los listados principales y el core render con `innerHTML`, y `refreshSidebar()` quedó compartido
- **Docs**: ROADMAP y LEGOS_AUDIT alineados con el estado real del refactor

## [v0.0.53] — 2026-06-13 — [Detalle](changelogs/v0.0.53.md)
- **Tests**: 14 new test files (LLM, context, web, integration, smoke), 642 unit tests passing
- **Test fixes**: Cache isolation, mock patterns, audio data validation, FALLBACK_MODEL assertions
- **Docs**: README, config.py, LEGOS_AUDIT aligned; `src/api/_widget_helpers.py` bridge created
- **Smoke test**: 8 critical endpoint checks (homepage, session, sidebar, messages, debug, health, chat, streaming)

## [v0.0.52] — 2026-06-13 — [Detalle](changelogs/v0.0.52.md)
- **Lego refactor**: ModelState class, policy split (4 sub-modules), repos injection in tool_loop/orchestrator/router
- **Data access**: `sqlite3.Row` named access, 38 positional→named migrations, `chat_sync` delegation
- **Retry**: Save retry exponential backoff, mid-stream recovery, StreamRetryHandler wired, rate limiter del bug fixed
- **Frontend**: 78 inline CSS→classes, logUI/logStream extracted to standalone module, globals removed, `shared-state.js` created
- **Tools**: `git_operation` added (16 tools total), `MemoryIndexRepository` created
- **Audit & fixes**: 24 issues fixed (NameError bug, wildcard import, KairosWidgets dead code, widget-detector, docs, etc.)
- **Tests**: 523 Python + **176 Vitest passing (0 failures)**, 0 ESLint errors
- **Docs**: README, ARCHITECTURE, ARCHITECTURE_SUMMARY, MODULES, AGENTS all updated

## [v0.0.45] — 2026-06-12 — [Detalle](changelogs/v0.0.45.md)
- Officialized the new `execute_command` tool and the improved `list_files` tool in the public docs and tests
- Updated the tool architecture docs to reflect the 12-tool registry at that point in time
- Continued the historical hygiene pass by aligning the release notes with the runtime state of that release

## [v0.0.44] — 2026-06-12 — [Detalle](changelogs/v0.0.44.md)
- Removed the remaining compatibility shims from `src.core`, `src.llm`, `src.api`, and `src.memory`
- Aligned the public docs and README with the runtime modules and boundaries at that release
- Verified the cleaned runtime with the focused Python test batch

## [v0.0.43] — 2026-06-12 — [Detalle](changelogs/v0.0.43.md)
- Decoupled rate-limit retry logic into a reusable `src/llm/retry.py` wrapper and central config `src/constants.py`
- Optimized unit tests runtimes by patching `time.sleep` (reduced from 43s to 12s)
- Fixed loop detection false positives by tracking absolute backticks across truncation, and suspended phrase check in widget mode
- Symmetrically aligned client-side and server-side widget extractors to ignore widget patterns inside standard code blocks and backticks
- Fixed offset index shifting bug in `widget-container-renderer.js` and disabled verbose client-side logs to preserve Celerona SUMA C10 TDP

## [v0.0.42] — 2026-06-12 — [Detalle](changelogs/v0.0.42.md)
- Rate-limit errors now surface the provider reset window when headers expose it, and the UI shows the interruption reason instead of a generic failure
- The model selector now reads local model metadata and shows context / modality / capability labels instead of raw ids only
- Empty replies no longer auto-retry after reasoning or tool activity, which cuts the retry loop that amplified stream cutoffs
- `config.py` now accepts a fallback OpenCode API key env var before failing startup

## [v0.0.41] — 2026-06-12 — [Detalle](changelogs/v0.0.41.md)
- Removed the last lazy `src.api.messages` import from `tool_loop.py` by writing assistant turns through `src.memory.repos.MessageRepository` directly
- Kept the core runtime off the API facade while preserving compatibility for web and CLI callers
- Revalidated the Python core and frontend test batches after the persistence seam change

## [v0.0.40] — 2026-06-12 — [Detalle](changelogs/v0.0.40.md)
- Removed `src.core._deps` from the active runtime path by wiring `tool_loop.py` and `orchestrator.py` directly to `src.llm.client` and `src.tools`
- Updated the core test suite to patch the direct seams instead of the old compatibility wrapper
- Aligned the architecture docs with the new runtime boundary

## [v0.0.39] — 2026-06-12 — [Detalle](changelogs/v0.0.39.md)
- Removed the last `window.*` checks from the session reset path in `web/static/chat-stream.js`
- Kept the compatibility bootstraps intact but moved the active reset path to direct module calls
- Revalidated the main Python and frontend tests after the cleanup

## [v0.0.38] — 2026-06-12 — [Detalle](changelogs/v0.0.38.md)
- Removed the last internal `src.memory.database` dependencies from `src.memory` and `src.api.database`
- Pointed memory package exports, repository helpers, and DB checks directly at `src.memory.connection` and `src.memory.schema`
- Aligned the web architecture docs with the current connection/schema boundary

## [v0.0.37] — 2026-06-12 — [Detalle](changelogs/v0.0.37.md)
- Removed internal runtime dependence on `src.api.database` by wiring app bootstrap and health checks directly to `src.memory`
- Kept `src.api` and `src.memory.database` as compatibility shims only
- Confirmed the current runtime still passes Python and JS validation after the cleanup

## [v0.0.36] — 2026-06-12 — [Detalle](changelogs/v0.0.36.md)
- Split database lifecycle into `src/memory/connection.py` and `src/memory/schema.py`
- Kept `src/memory/database.py` as a compatibility wrapper for callers and tests
- Updated memory and architecture docs to reflect the new persistence boundaries

## [v0.0.35] — 2026-06-12 — [Detalle](changelogs/v0.0.35.md)
- Split LLM lifecycle policy into `src/llm/policy.py` and kept `src/llm/manager.py` as a compatibility wrapper
- Pointed the runtime `src.llm` entrypoint and client failover at the new policy module
- Updated the LLM docs, contracts, and architecture summaries to match the new boundary

## [v0.0.34] — 2026-06-12 — [Detalle](changelogs/v0.0.34.md)
- Removed the last remaining inline-ish UI handlers by delegating debug copy actions and retry handling
- Removed duplicate bootstrap initialization so `chat-stream.js` owns startup once
- Updated the contracts and audit docs to reflect the narrower UI startup surface

## [v0.0.33] — 2026-06-12 — [Detalle](changelogs/v0.0.33.md)
- Removed duplicate bootstrap initialization so `chat-stream.js` owns the runtime setup once
- Left the widget and chat-form bootstraps as compatibility globals only
- Kept the bundle and frontend tests green after the startup path got narrower

## [v0.0.32] — 2026-06-12 — [Detalle](changelogs/v0.0.32.md)
- Removed the last inline HTML handlers from the runtime UI, including the debug copy buttons and retry button
- Moved model selector binding into `web/static/session.js` and kept the template as pure state markup
- Updated the legos audit and frontend architecture docs to reflect the now handler-free HTML surface

## [v0.0.31] — 2026-06-12 — [Detalle](changelogs/v0.0.31.md)
- Removed the empty `stream-renderer.js` loader and its template include
- Trimmed the production bundle again after the dead frontend edge disappeared
- Kept the architecture docs aligned with the now smaller runtime surface

## [v0.0.30] — 2026-06-12 — [Detalle](changelogs/v0.0.30.md)
- Reduced `web/static/app.js` to a pure assembly entry and moved all legacy globals into the dedicated bootstraps
- Updated frontend architecture docs and the legos audit to describe bootstraps as the only compatibility surface
- Kept the bundle build passing with the narrower entry boundary

## [v0.0.29] — 2026-06-12 — [Detalle](changelogs/v0.0.29.md)
- Split the bundled frontend entry into `web/static/app.js` and removed the obsolete `web/static/main.js` wrapper
- Updated Vite to build from the explicit app entry and validated the bundle
- Synchronized the frontend architecture docs and legos audit with the new entry/wrapper boundary

## [v0.0.28] — 2026-06-12 — [Detalle](changelogs/v0.0.28.md)
- Added `docs/LEGOS_AUDIT.md` with a full decoupling/backlog audit
- Replaced sidebar `onclick="loadSession(...)"` with delegated clicks in `web/static/session.js`
- Aligned session tests with the imported loadSession seam

## [v0.0.27] — 2026-06-12 — [Detalle](changelogs/v0.0.27.md)
- Split database lifecycle from connection reuse with a per-path initialization guard
- Removed the unused `get_verified_models()` export from `src.api.chat`
- Updated memory and contract docs to match the current DB and facade boundaries

## [v0.0.26] — 2026-06-12 — [Detalle](changelogs/v0.0.26.md)
- Removed the shared `_get_repo()` registry and moved runtime callers to module-level repository singletons
- Trimmed `src/api/_repos.py` out of the runtime path and aligned the remaining facade/tests to the direct seams
- Updated architecture docs so the repository/cache story matches the code

## [v0.0.25] — 2026-06-12 — [Detalle](changelogs/v0.0.25.md)
- Stream contract shared between Python and JS, widget bootstrap split, dev server split, API facade trimmed
- Page/model startup no longer blocks requests, `src.core._deps` moved from partials to explicit wrappers, sync save path fixed without reintroducing a core cycle
- 19 Python integration/unit tests and 43 JS tests validated on the new borders

## [v0.0.24] — 2026-06-12 — [Detalle](changelogs/v0.0.24.md)
- DOM ordering, loop detector v2 (context-aware), transparent retry handler
- getPhaseIndex fix, 18 Python test repairs (0 failures), 591 tests total

## [v0.0.23] — 2026-06-10 — [Detalle](changelogs/v0.0.23.md)
- Widget rendering fixes, stream stability, history sanitizer, backend logging

## [v0.0.22] — 2026-06-10 — [Detalle](changelogs/v0.0.22.md)
- Widget deduplication, iframe height auto, toolbar flex-wrap, placeholder fix

## [v0.0.21] — 2026-06-11 — [Detalle](changelogs/v0.0.21.md)
- ESLint 0 errores, circular import fix, flaky test fix, final cleanup

## [v0.0.20] — 2026-06-11 — [Detalle](changelogs/v0.0.20.md)
- ESLint 0 errores, circular import tool_loop→api, flaky test fix

## [v0.0.19] — 2026-06-11 — [Detalle](changelogs/v0.0.19.md)
- ESLint globals, docs update, fetch .catch()

## [v0.0.18] — 2026-06-11 — [Detalle](changelogs/v0.0.18.md)
- Architecture docs (8 archivos), CHANGELOG/README/ROADMAP updated

## [v0.0.17] — 2026-06-11 — [Detalle](changelogs/v0.0.17.md)
- LLM models split, client dedup, frontend refactor, SessionRepository, path DRY

## [v0.0.16] — 2026-06-11 — [Detalle](changelogs/v0.0.16.md)
- Documentation update, dead code cleanup, N+1 fix, frontend fixes

## [v0.0.15] — 2026-06-11 — [Detalle](changelogs/v0.0.15.md)
- 30 new tests, DRY helpers, lazy lxml, flaky test fix

## [v0.0.14] — 2026-06-11 — [Detalle](changelogs/v0.0.14.md)
- Security (XSS, debug access), Docker, CI, healthcheck

## [v0.0.13] — 2026-06-11 — [Detalle](changelogs/v0.0.13.md)
- ES modules migration, Vite, circular imports fix

## [v0.0.12] — 2026-06-11 — [Detalle](changelogs/v0.0.12.md)
- Dependency injection, circular imports fix via DI container

## [v0.0.11] — 2026-06-11 — [Detalle](changelogs/v0.0.11.md)
- api.py split (226→10 modules), E2E expansion

## [v0.0.10] — 2026-06-11 — [Detalle](changelogs/v0.0.10.md)
- chat-form split, toolbar split, session error handling, dead code

## [v0.0.9] — 2026-06-11 — [Detalle](changelogs/v0.0.9.md)
- Playwright E2E setup, -1420 lines cleanup

## [v0.0.8] — 2026-06-11 — [Detalle](changelogs/v0.0.8.md)
- Vitest migration, type hints, error boundaries, API contract tests

## [v0.0.7] — 2026-06-11 — [Detalle](changelogs/v0.0.7.md)
- Architecture refactor: context→package, history→3 modules, runner→4 modules
- DatabaseEngine Protocol, Provider injection, Circular deps broken

## [v0.0.6] — 2026-06-11 — [Detalle](changelogs/v0.0.6.md)
- Ruff 71→0, Pyright 16→0, refactors, 45 JS tests

## [v0.0.5] — 2026-06-11 — [Detalle](changelogs/v0.0.5.md)
- Health audit, 10 fixes, repos extraction, tools unification

## [v0.0.4] — 2026-06-11 — [Detalle](changelogs/v0.0.4.md)
- Security: CSP, SSRF, XSS, rate limiting, debug auth
- DB: migration 010, FK constraints, cascade deletes
- 6 critical bugs fixed, architecture refactor

## [v0.0.3] — 2026-06-08 — [Detalle](changelogs/v0.0.3.md)
- API Facade, Repository Pattern, Thread safety, Migrations

## [v0.0.2] — 2026-06-08 — [Detalle](changelogs/v0.0.2.md)
- Architecture Lego, Real streaming, Fallback, Widget system, Dashboard

## [v0.0.1] — 2026-06-08 — [Detalle](changelogs/v0.0.1.md)
- Chat funcional (CLI + Web), SQLite, Tools auto-discovery, Basic architecture
