#!/usr/bin/env python3
"""Diagnose provider rejections — trace full request lifecycle with timing.

Usage:
    python scripts/diag_provider.py "hola, como estas?" [--model deepseek-v4-flash] [--retries 3]

Shows:
- Each step timing (system prompt, history, messages, API call)
- Raw request body sent to provider
- Provider response or error details
- Retry attempts and fallback models
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    parser = argparse.ArgumentParser(description="Diagnose provider rejections")
    parser.add_argument("message", nargs="?", default="hola, como estas?", help="Test message")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()

    print("=" * 60)
    print("🔬 Provider Diagnostic")
    print(f"   Message: {args.message[:80]}...")
    print(f"   Model:   {args.model}")
    print(f"   Retries: {args.retries}")
    print("=" * 60)

    # ── Step 1: Load config ──────────────────────────────────────
    t0 = time.monotonic()
    from src.config_loader import load_config
    cfg = load_config()
    print(f"\n[{(time.monotonic()-t0)*1000:6.0f}ms] Config loaded")

    # ── Step 2: Build system prompt ──────────────────────────────
    t0 = time.monotonic()
    from src.context.builder import build_system_prompt
    try:
        system_prompt = build_system_prompt(args.model)
        print(f"[{(time.monotonic()-t0)*1000:6.0f}ms] System prompt: {len(system_prompt)} chars")
    except Exception as e:
        print(f"[{(time.monotonic()-t0)*1000:6.0f}ms] System prompt FAILED: {e}")
        system_prompt = "You are a helpful assistant."

    # ── Step 3: Prepare messages ─────────────────────────────────
    t0 = time.monotonic()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": args.message},
    ]
    print(f"[{(time.monotonic()-t0)*1000:6.0f}ms] Messages prepared: {len(messages)} total")

    # ── Step 4: Try API call ─────────────────────────────────────
    from src.llm.adapters.openai_adapter import OpenAIAdapter
    from src.llm.protocol import UnifiedRequest

    adapter = OpenAIAdapter(
        api_key=cfg.opencode_zen_api_key or "no-key",
        base_url=getattr(cfg, "opencode_zen_base_url", "https://opencode.ai/zen/go/v1") or "https://opencode.ai/zen/go/v1",
    )

    for attempt in range(1, args.retries + 1):
        t0 = time.monotonic()
        print(f"\n── Attempt {attempt}/{args.retries} ──")

        # Sanitize messages
        t1 = time.monotonic()
        openai_messages = adapter._to_openai_messages(messages)
        print(f"[{(time.monotonic()-t1)*1000:6.0f}ms] Messages sanitized: {len(openai_messages)} msgs")

        # Show message structure
        for i, m in enumerate(openai_messages):
            keys = list(m.keys())
            sizes = {k: len(str(v)) for k, v in m.items()}
            print(f"   msg[{i}] role={m.get('role','?')} keys={keys} sizes={sizes}")

        # Build request
        request = UnifiedRequest(
            model=args.model,
            messages=messages,  # raw messages (adapter handles sanitization)
            tools=None,
            temperature=None,
            max_tokens=32768,
        )

        try:
            t_api = time.monotonic()
            chunks = 0
            first_token = None
            content_parts = []
            async for event in adapter.chat_stream(request):
                chunks += 1
                if first_token is None and event.delta:
                    first_token = time.monotonic()
                if event.delta:
                    content_parts.append(event.delta)
            elapsed = (time.monotonic() - t_api) * 1000
            ttft = (first_token - t_api) * 1000 if first_token else None
            content = "".join(content_parts)
            print(f"[{elapsed:6.0f}ms] ✅ SUCCESS — {chunks} chunks, {len(content)} chars content")
            if ttft:
                print(f"[{elapsed:6.0f}ms]    TTFT: {ttft:.0f}ms")
            return 0

        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            err_type = type(e).__name__
            err_str = str(e)[:300]
            print(f"[{elapsed:6.0f}ms] ❌ {err_type}: {err_str}")

            # Show full traceback for debugging
            if hasattr(e, '__cause__') and e.__cause__:
                cause_type = type(e.__cause__).__name__
                cause_str = str(e.__cause__)[:200]
                print(f"   Caused by: {cause_type}: {cause_str}")

            if attempt < args.retries:
                delay = 2 * attempt
                print(f"   Retrying in {delay}s...")
                await asyncio.sleep(delay)

    print("\n❌ All attempts failed")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
