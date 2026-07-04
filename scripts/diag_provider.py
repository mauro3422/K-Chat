#!/usr/bin/env python3
"""Deep provider diagnostic — stress-test the full pipeline to find failure patterns.

Usage:
    python scripts/diag_provider.py              # run all tests
    python scripts/diag_provider.py --quick       # just 2 fast tests
    python scripts/diag_provider.py --model deepseek-v4-flash --message "hola"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def test_one(name: str, message: str, model: str, with_tools: bool = False) -> dict:
    """Run a single test and return timing/error info."""
    from src.config_loader import load_config
    from src.context.builder import build_system_prompt
    from src.llm.adapters.openai_adapter import OpenAIAdapter
    from src.llm.protocol import UnifiedRequest

    cfg = load_config()
    # Use the correct base URL based on llm_mode (go → go URL, else → zen URL)
    base_url = getattr(cfg, "opencode_go_base_url", None) if getattr(cfg, "llm_mode", "go") == "go" else getattr(cfg, "opencode_zen_base_url", None)
    base_url = base_url or "https://opencode.ai/zen/go/v1"
    result = {"name": name, "model": model, "msg_len": len(message), "tools": with_tools}

    try:
        system_prompt_raw = build_system_prompt(model)
        if isinstance(system_prompt_raw, dict):
            system_prompt = json.dumps(system_prompt_raw)
        else:
            system_prompt = str(system_prompt_raw) if system_prompt_raw else "You are a helpful assistant."
    except Exception as e:
        system_prompt = "You are a helpful assistant."
        result["sp_error"] = str(e)[:100]

    result["sp_len"] = len(system_prompt)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    tools = None
    if with_tools:
        tools = [{
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Get current time",
                "parameters": {"type": "object", "properties": {}}
            }
        }]

    adapter = OpenAIAdapter(
        api_key=cfg.opencode_zen_api_key or "",
        base_url=base_url,
    )

    t0 = time.monotonic()
    try:
        openai_messages = adapter._to_openai_messages(messages)
        result["msg_keys"] = [list(m.keys()) for m in openai_messages]
        result["msg_sizes"] = {m["role"]: sum(len(str(v)) for v in m.values()) for m in openai_messages}

        request = UnifiedRequest(
            model=model, messages=messages, tools=tools,
            temperature=None, max_tokens=4096,
        )

        chunks = 0
        first_token_ts = None
        content = []
        reasoning = []
        tool_calls_seen = 0
        errors_seen = []

        async for event in adapter.chat_stream(request):
            # adapter yields tuples (event_type, delta) not objects
            ev_type = event[0] if isinstance(event, tuple) else getattr(event, 'event_type', '?')
            delta = event[1] if isinstance(event, tuple) else getattr(event, 'delta', '')
            chunks += 1
            if first_token_ts is None:
                first_token_ts = time.monotonic()
            if ev_type == "content" and delta:
                content.append(delta)
            elif ev_type == "reasoning" and delta:
                reasoning.append(delta)
            elif ev_type == "tool_call":
                tool_calls_seen += 1
            elif ev_type == "error":
                errors_seen.append(delta)

        elapsed_ms = (time.monotonic() - t0) * 1000
        ttft_ms = (first_token_ts - t0) * 1000 if first_token_ts else None

        result["ok"] = True
        result["elapsed_ms"] = round(elapsed_ms)
        result["ttft_ms"] = round(ttft_ms) if ttft_ms else None
        result["chunks"] = chunks
        result["content_len"] = len("".join(content))
        result["reasoning_len"] = len("".join(reasoning))
        result["tool_calls"] = tool_calls_seen
        result["errors"] = errors_seen

    except Exception as e:
        elapsed_ms = (time.monotonic() - t0) * 1000
        result["ok"] = False
        result["elapsed_ms"] = round(elapsed_ms)
        result["error_type"] = type(e).__name__
        result["error_msg"] = str(e)[:400]
        if hasattr(e, '__cause__') and e.__cause__:
            result["cause_type"] = type(e.__cause__).__name__
            result["cause_msg"] = str(e.__cause__)[:200]

    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--message", default=None)
    parser.add_argument("--smoke", action="store_true", help="Smoke test mode: exit non-zero on any failure")
    args = parser.parse_args()

    if args.message:
        # Single test mode
        r = await test_one("single", args.message, args.model)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0 if r.get("ok") else 1

    # ── Test matrix ────────────────────────────────────────────
    tests = [
        ("short_no_tools", "hola", False),
        ("medium_no_tools", "explicame brevemente que es Python y para que sirve", False),
        ("long_no_tools", "explicame detalladamente la diferencia entre una lista y una tupla en Python, con ejemplos de codigo y casos de uso. tambien explicame cuando conviene usar cada una.", False),
        ("short_with_tools", "que hora es?", True),
    ]

    if not args.quick:
        tests += [
            ("short_no_tools", "hola", False),  # repeat to check consistency
            ("medium_no_tools", "cual es la capital de Francia?", False),
            ("short_no_tools", "como estas?", False),
        ]

    print(f"{'Test':<25} {'Model':<22} {'Msg':>5} {'SP':>6} {'TTFT':>6} {'Total':>7} {'Chunks':>7} {'Content':>8} {'Status'}")
    print("-" * 110)

    ok = 0
    fail = 0
    results = []

    for name, msg, tools in tests:
        r = await test_one(name, msg, args.model, tools)
        results.append(r)

        status = "✅" if r.get("ok") else f"❌ {r.get('error_type','?')}"
        ttft = f"{r.get('ttft_ms','-')}ms" if r.get('ttft_ms') else "-"
        total = f"{r.get('elapsed_ms','-')}ms"
        chunks = str(r.get('chunks', '-'))
        clen = str(r.get('content_len', '-'))

        print(f"{r['name']:<25} {r['model']:<22} {r['msg_len']:>5} {r['sp_len']:>6} {ttft:>6} {total:>7} {chunks:>7} {clen:>8} {status}")

        if r.get("ok"):
            ok += 1
        else:
            fail += 1
            # Show error detail for failures
            print(f"  └─ {r.get('error_type','?')}: {r.get('error_msg','')[:150]}")
            if r.get('cause_msg'):
                print(f"     Caused by: {r.get('cause_type','?')}: {r['cause_msg'][:150]}")

        await asyncio.sleep(1)  # avoid rate limiting ourselves

    print(f"\n✅ {ok} passed, ❌ {fail} failed out of {ok+fail}")

    # Show patterns
    if fail > 0:
        print("\n── Failure patterns ──")
        error_types = {}
        for r in results:
            if not r.get("ok"):
                et = r.get("error_type", "?")
                error_types[et] = error_types.get(et, 0) + 1
        for et, count in sorted(error_types.items()):
            print(f"  {et}: {count}x")

    if args.smoke:
        if fail > 0:
            print("\n❌ SMOKE TEST FAILED")
            return 1
        print("\n✅ SMOKE TEST PASSED")
        return 0

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
