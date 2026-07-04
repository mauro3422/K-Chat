#!/usr/bin/env python3
"""Simulate multi-turn chat to find the second-message failure pattern.

The bug: first message works, second message fails with
"Messages with role 'tool' must be a response to a preceding message with 'tool_calls'"

Usage: python scripts/diag_chat_sim.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def simulate_turn(session_id: str, message: str, model: str, turn: int) -> dict:
    """Simulate one chat turn through the full pipeline."""
    from src.config_loader import load_config
    from src.api.repos import get_repos, MessageRecord, DebugInfo
    from src.core.history_rebuilder import rebuild_history
    from src.context.builder import build_system_prompt
    from src.llm.adapters.openai_adapter import OpenAIAdapter
    from src.llm.protocol import UnifiedRequest

    cfg = load_config()
    repos = get_repos()
    result = {"turn": turn, "message": message[:60]}

    # ── Step 1: Save user message and rebuild history ──────────
    t0 = time.monotonic()
    await repos.sessions.ensure(session_id)
    await repos.messages.save(session_id, role="user", content=message, model=model)
    result["save_user_ms"] = round((time.monotonic() - t0) * 1000)

    # ── Step 2: Rebuild history ───────────────────────────────
    t0 = time.monotonic()
    try:
        history = await rebuild_history(session_id, model, messages_repo=repos.messages)
        result["history_len"] = len(history)
    except Exception as e:
        result["history_error"] = str(e)[:200]
        return result
    result["rebuild_ms"] = round((time.monotonic() - t0) * 1000)

    # ── Step 3: Build system prompt ───────────────────────────
    t0 = time.monotonic()
    try:
        sp = build_system_prompt(model)
        if isinstance(sp, dict):
            sp = json.dumps(sp)
    except Exception:
        sp = "You are a helpful assistant."
    result["sp_len"] = len(str(sp))
    result["sp_ms"] = round((time.monotonic() - t0) * 1000)

    # ── Step 4: Add system prompt ─────────────────────────────
    history.insert(0, {"role": "system", "content": str(sp)})

    # ── Step 5: Analyze history for tool patterns ─────────────
    tool_count = sum(1 for m in history if m.get("role") == "tool")
    assistant_tc_count = sum(1 for m in history if m.get("role") == "assistant" and m.get("tool_calls"))
    result["tool_msgs"] = tool_count
    result["assistant_tc_msgs"] = assistant_tc_count

    # Check for orphaned tools
    orphans = []
    for i, m in enumerate(history):
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id", "")
            # Find preceding assistant with matching tool_calls
            found = False
            for j in range(i - 1, -1, -1):
                prev = history[j]
                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                    tc_ids = [tc.get("id", "") for tc in prev["tool_calls"]]
                    if tcid in tc_ids:
                        found = True
                        break
            if not found:
                orphans.append({"idx": i, "tool_call_id": tcid[:40]})
    result["orphan_tools"] = len(orphans)
    if orphans:
        result["orphan_details"] = orphans[:3]

    # ── Step 6: Sanitize and try LLM call ─────────────────────
    adapter = OpenAIAdapter(
        api_key=cfg.opencode_zen_api_key or "",
        base_url=getattr(cfg, "opencode_go_base_url", None) or "https://opencode.ai/zen/go/v1",
    )

    t0 = time.monotonic()
    try:
        openai_msgs = adapter._to_openai_messages(history)
        result["openai_msg_count"] = len(openai_msgs)
        # Show last 5 messages for debugging
        result["last_msgs"] = [
            {"role": m.get("role"), "has_tc": bool(m.get("tool_calls")),
             "has_tcid": bool(m.get("tool_call_id")),
             "content_len": len(str(m.get("content", "")))}
            for m in openai_msgs[-5:]
        ]
    except Exception as e:
        result["sanitize_error"] = str(e)[:200]
        return result

    t0 = time.monotonic()
    try:
        request = UnifiedRequest(model=model, messages=history, tools=None,
                                  temperature=None, max_tokens=200)
        chunks = 0
        content_parts = []
        tool_call_chunks: dict[int, dict] = {}  # index → {id, name, args}
        first_token = None
        async for ev_type, delta in adapter.chat_stream(request):
            chunks += 1
            if first_token is None:
                first_token = time.monotonic()
            if ev_type == "content":
                content_parts.append(delta)
            elif ev_type == "tool_call":
                # Accumulate tool call deltas (indexed by call index)
                idx = delta.index
                if idx not in tool_call_chunks:
                    tool_call_chunks[idx] = {"id": delta.id or "", "name": "", "arguments": ""}
                if delta.name:
                    tool_call_chunks[idx]["name"] = delta.name
                if delta.arguments:
                    tool_call_chunks[idx]["arguments"] += delta.arguments

        full_content = "".join(content_parts)

        # Build final tool_calls list from accumulated deltas
        tool_calls = []
        for idx in sorted(tool_call_chunks):
            tc = tool_call_chunks[idx]
            tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                }
            })

        result["ok"] = True
        result["chunks"] = chunks
        result["has_tool_calls"] = len(tool_calls) > 0
        result["tool_call_count"] = len(tool_calls)
        if full_content:
            result["content"] = full_content[:200]
        result["api_ms"] = round((time.monotonic() - t0) * 1000)
        result["ttft_ms"] = round((first_token - t0) * 1000) if first_token else None

        # Save assistant response — include tool_calls if present
        tc_json = json.dumps(tool_calls) if tool_calls else None
        content_to_save = full_content if full_content else None
        # Only save if we have content OR tool_calls (not an empty bubble)
        if content_to_save or tc_json:
            await repos.messages.save(
                session_id, role="assistant",
                content=content_to_save,
                tool_calls=tc_json if tc_json != "[]" else None,
                model=model,
            )
        else:
            result["saved"] = False
            result["note"] = "Empty response (no content, no tool_calls) — not saved"

    except Exception as e:
        result["ok"] = False
        result["error_type"] = type(e).__name__
        result["error_msg"] = str(e)[:300]
        result["api_ms"] = round((time.monotonic() - t0) * 1000)

    return result


async def main():
    session_id = f"diag-multi-{uuid.uuid4().hex[:8]}"
    model = "deepseek-v4-flash"

    print("=" * 70)
    print(f"🔬 Multi-turn Chat Simulation — session: {session_id[:20]}")
    print("=" * 70)

    # ── Turn 1: Simple message, should trigger tools ──────────
    print("\n── Turn 1: Message that triggers tools ──")
    r1 = await simulate_turn(session_id, "busca en google noticias de tecnologia de hoy", model, 1)
    _print_result(r1)

    await asyncio.sleep(2)

    # ── Turn 2: Follow-up message ─────────────────────────────
    print("\n── Turn 2: Follow-up (should use history with tools) ──")
    r2 = await simulate_turn(session_id, "gracias, ahora explicame que es Python", model, 2)
    _print_result(r2)

    await asyncio.sleep(2)

    # ── Turn 3: Another follow-up ─────────────────────────────
    print("\n── Turn 3: Another message ──")
    r3 = await simulate_turn(session_id, "como estas?", model, 3)
    _print_result(r3)

    # Summary
    print(f"\n{'='*70}")
    results = [r1, r2, r3]
    ok = sum(1 for r in results if r.get("ok"))
    fail = sum(1 for r in results if not r.get("ok"))
    print(f"Summary: {ok}/{len(results)} OK, {fail} failed")

    if fail > 0:
        print("\nFailures:")
        for r in results:
            if not r.get("ok"):
                print(f"  Turn {r['turn']}: {r.get('error_type','?')} — {r.get('error_msg','')[:200]}")
                if r.get("orphan_tools", 0) > 0:
                    print(f"    Orphan tools: {r['orphan_tools']}")


def _print_result(r):
    status = "✅" if r.get("ok") else f"❌ {r.get('error_type','?')}"
    print(f"  History: {r.get('history_len','?')} msgs, tools: {r.get('tool_msgs','?')}, "
          f"assistant_tc: {r.get('assistant_tc_msgs','?')}, orphans: {r.get('orphan_tools','?')}")
    print(f"  SP: {r.get('sp_len','?')} chars, openai_msgs: {r.get('openai_msg_count','?')}")
    if r.get("ok"):
        tc_info = f" tool_calls={r.get('tool_call_count','?')}" if r.get('has_tool_calls') else ""
        print(f"  {status} TTFT={r.get('ttft_ms','?')}ms, {r.get('chunks','?')} chunks,{tc_info} "
              f"content={r.get('content','')[:80]}...")
        if r.get("note"):
            print(f"  ⚠️  {r['note']}")
    else:
        print(f"  {status}: {r.get('error_msg','')[:150]}")
        if r.get("last_msgs"):
            print(f"  Last msgs: {r['last_msgs']}")


if __name__ == "__main__":
    asyncio.run(main())
