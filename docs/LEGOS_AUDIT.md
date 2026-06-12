# K-Chat Legos Audit

This is the current architecture audit for the repo. It is intentionally blunt: the goal is to separate what is already decoupled from what is only "working through compatibility."

## What "repos" means here

The repository pattern is not the same thing as "the system is fully decoupled."

What it gives us:
- one place that knows the table shape and SQL
- one place to test persistence behavior
- a narrow seam that services, tools, and routers can call
- a boundary where DB details stop leaking into the rest of the app

What it does not automatically give us:
- no globals
- no hidden singleton state
- no facade that re-exports everything
- no direct access to private repo methods
- no cross-layer assumptions about schema or transaction policy

For this project, "ready" means:
- the rest of the code never writes raw SQL
- services use repo methods, not repo internals
- each repo owns one responsibility
- cross-repo orchestration happens in a higher layer explicitly
- tests patch the seam owned by the module, not a generic cache object

That is a strong decoupling step, but not the final state of the system.

## What is already in good shape

These are the seams I would keep:

- `web/services/stream_contract.py` and `web/static/modules/stream-contract.js`
- `web/services/widget_contract.py` and `web/static/modules/widgets/contract.js`
- `src/memory/repos/*`
- `web/app_factory.py`
- `web/dev_server.py`
- `web/routers/*`
- `src/tools/loader.py` plus the `DEFINITION`/`run()` tool convention
- `web/services/message_persister.py`
- `web/services/stream_error_classifier.py`
- `web/static/modules/widgets/state-manager.js`
- `web/static/modules/stream-dispatcher.js`

These are already close to the "lego" ideal because they have clear owners and fairly stable boundaries.

## What is still compatibility-first

These modules are still mostly there to keep old callers alive:

- `src/api/__init__.py`
- `api modules for session and db were split`
- `src/api/chat.py`
- `web/static/app.js`
- `web/static/modules/widgets/bootstrap.js`
- `web/static/modules/stream-bootstrap.js`
- `web/static/modules/chat-form-bootstrap.js`
- `web/static/session.js`
- `web/static/debug.js`
- `web/static/chat-stream.js`

Compatibility is not bad, but it should be obvious in the code and docs that these are transition surfaces, not the model for new work.

## Remaining coupling, by area

### 1. API facade

Current state:
- `src/api/__init__.py` is a compatibility facade, which is correct.
- The facade is still wide and flat.
- Some callers still import through it by habit.

What still bothers me:
- the facade is still a default mental model in docs
- domain-level imports are not yet the universal norm

Best next cut:
- keep shrinking the exports in `src/api/__init__.py`
- stop describing it as the primary entry point anywhere in the docs

### 2. LLM routing

Current state:
- `src/llm/policy.py` does discovery, verification, default selection, and refresh policy
- `llm policy moved to src/llm/policy.py` is now a compatibility wrapper around that policy
- `src/llm/model_state.py` holds shared state
- `src/llm/client.py` does runtime failover

What still bothers me:
- the policy boundary still deserves smaller sub-pieces
- model verification is still a live behavior, not just cached state
- selection logic still has special cases that are easy to forget

Best next cut:
- split the model lifecycle into smaller concepts:
  - discovery
  - verification
  - selection
  - failover policy

That would make the LLM layer read more like a set of lego pieces and less like a smart helper module.

### 3. Database lifecycle

Current state:
- `src/memory/connection.py` guards per-thread pooled connections
- `src/memory/schema.py` guards init per DB path
- `src/memory/repos/*` are the actual persistence units
- `src/memory/repos/base.py` owns transaction behavior

What still bothers me:
- `get_conn()` and `init_db()` still live in the same module
- the module still knows about path resolution, engine selection, connection reuse, and migration execution

Best next cut:
- split lifecycle into:
  - connection factory
  - schema/init runner
  - migration executor
  - engine adapter

This is one of the few places where further decomposition still looks valuable.

### 4. Frontend compatibility shims

Current state:
- `window` is still used intentionally in a few places
- `app.js` is the actual bundle entry and keeps the assembly logic only
- `session.js`, `debug.js`, `chat-stream.js`, and the bootstrap modules still bridge old and new entry styles

What still bothers me:
- `window.*` is still more common than it should be
- a few legacy globals still exist for transition surfaces
- compatibility globals are isolated in the bootstraps now, not in `app.js`

Best next cut:
- keep globals only where legacy entrypoints truly need them
- continue removing globals from the bootstraps only if the legacy surface is no longer needed

### 5. Documentation drift

Current state:
- some docs already reflect the newer design
- some docs still describe old coupling patterns

Docs that currently lag reality:
- `docs/ARCHITECTURE_FRONTEND.md`
- `docs/llm_architecture.md`
- `docs/tools-architecture.md`
- `docs/HEALTH.md`
- parts of `docs/MODULES.md`

What still bothers me:
- the docs tell two stories at once
- new architecture decisions are not consistently reflected

Best next cut:
- either update these docs in one pass, or mark them clearly as historical

## Prioritized backlog

### P0

1. Reduce the compatibility bootstraps if the legacy surface is no longer needed.
2. Keep shrinking legacy globals and transition surfaces where practical.
3. Split `src/llm/policy.py` into smaller policy objects or modules.
4. Split `memory connection + schema + repos` into lifecycle pieces.

### P1

1. Continue shrinking `src/api/__init__.py`.
2. Keep moving old callers to direct domain imports.
3. Update the stale architecture docs to match runtime reality.

### P2

1. Reduce compatibility aliases in `session.js`, `debug.js`, and `chat-stream.js`.
2. Review whether `api modules for session and db were split` still deserves to exist as a facade.
3. Consider replacing the current `window` bridge pattern with explicit initialization objects where practical.

## What "done" looks like for this repo

I would consider the system meaningfully "lego" when:

- persistence lives behind repo methods only
- model selection is policy-driven and explicit
- frontend compatibility is isolated to a few bootstraps, not spread across the app
- the facade package is only for backwards compatibility
- docs mention the compatibility story honestly
- tests patch the seam owned by the module under test, not a generic helper cache

That is the closest practical version of "perfection" here.

## Recommendation

Do another audit after the P0 items above are cut. At that point the remaining work should be mostly compatibility cleanup and documentation sync, not structural rescue.
