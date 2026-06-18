#!/usr/bin/env python3
"""Nightly memory curator entry point for systemd timer.

Runs curate_all() with Gardener + Tracer + Curator.
Logs to journald via print (systemd captures stdout).
Exits with 0 on success, 1 on failure.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from src.memory.curator.curate import curate_all
    from src.tools.save_memory import run as save_memory_run
    
    print("🌙 K-Chat Memory Curator starting...")
    result = await curate_all(dry=False, save_memory_fn=lambda k, v: save_memory_run(key=k, value=v))
    
    gardener = result.get("gardener", [])
    tracer = result.get("tracer", {})
    entries = result.get("entries", [])
    saved = result.get("saved", 0)
    
    print(f"✅ Gardener: {len(gardener)} actions")
    for g in gardener:
        print(f"   {g['action']}: found={g.get('candidates_found',0)} processed={g.get('pruned',0)+g.get('merged',0)+g.get('archived',0)+g.get('removed',0)}")
    
    print(f"✅ Tracer: {tracer.get('total', 0)} patterns found")
    for p in tracer.get("patterns", [])[:5]:
        print(f"   [{p['type']}] ...")
    
    print(f"✅ Curator: {saved}/{len(entries)} new memories saved")
    
    if saved > 0 or gardener or tracer.get("total", 0) > 0:
        print("✅ Curation successful")
        sys.exit(0)
    else:
        print("ℹ️  Nothing to curate this cycle")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
