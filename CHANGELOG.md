# Changelog

> **Regla**: Este archivo es solo el índice. El detalle de cada versión está en `changelogs/vX.Y.Z.md`.
> Cada nueva versión DEBE crear su archivo correspondiente en `changelogs/` y agregarse aquí.

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
