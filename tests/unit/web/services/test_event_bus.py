"""Tests for the EventBus — in-memory pub/sub for SSE."""

import asyncio
import json
import pytest
from web.services.event_bus import EventBus, get_event_bus


pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def bus():
    return EventBus()


# ── 1. Subscribe and receive events ──────────────────────────────────────


async def test_subscribe_receive(bus):
    q = await bus.subscribe("client_1")
    await bus.publish("test_event", {"msg": "hello"})
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert event == {"type": "test_event", "data": {"msg": "hello"}}


# ── 2. Multiple subscribers ──────────────────────────────────────────────


async def test_multiple_subscribers_all_receive(bus):
    q1 = await bus.subscribe("c1")
    q2 = await bus.subscribe("c2")
    await bus.publish("hello", {"n": 42})
    r1 = await asyncio.wait_for(q1.get(), timeout=1)
    r2 = await asyncio.wait_for(q2.get(), timeout=1)
    assert r1 == r2 == {"type": "hello", "data": {"n": 42}}


# ── 3. Unsubscribe / client disconnect ───────────────────────────────────


async def test_unsubscribed_client_no_longer_receives(bus):
    q = await bus.subscribe("client_x")
    await bus.unsubscribe("client_x")
    await bus.publish("silent", "data")
    assert q.empty()


async def test_unsubscribe_unknown_client_does_not_raise(bus):
    await bus.unsubscribe("nonexistent")
    assert True


# ── 4. No channel support — publish reaches all subscribers ──────────────


async def test_publish_broadcasts_to_all_no_topic_filtering(bus):
    """EventBus has no channel/topic filtering — publish sends to every subscriber."""
    q1 = await bus.subscribe("a")
    q2 = await bus.subscribe("b")
    await bus.publish("global", True)
    assert await asyncio.wait_for(q1.get(), timeout=1)
    assert await asyncio.wait_for(q2.get(), timeout=1)


# ── 5. No subscribers — no error ─────────────────────────────────────────


async def test_publish_no_subscribers_no_error(bus):
    await bus.publish("lonely", {})
    await asyncio.sleep(0.05)
    assert True


# ── 6. Concurrent publish ────────────────────────────────────────────────


async def test_concurrent_publish_all_events_delivered(bus):
    queues = {}
    for i in range(3):
        queues[i] = await bus.subscribe(f"cc{i}")

    async def publisher(n):
        for i in range(10):
            await bus.publish("t", {"pub": n, "i": i})
            await asyncio.sleep(0.005)

    await asyncio.gather(*(publisher(n) for n in range(5)))

    for q in queues.values():
        received = 0
        while not q.empty():
            q.get_nowait()
            received += 1
        assert received == 50, f"Expected 50 events, got {received}"


# ── 7. Client reconnection via stream ────────────────────────────────────


async def test_stream_auto_subscribe_and_reconnect(bus):
    """stream() subscribes the client; after cancel it unsubscribes,
    so a second stream() call creates a fresh subscription."""
    async def collect(gen, n):
        results = []
        async for msg in gen:
            results.append(msg)
            if len(results) >= n:
                break
        return results

    gen1 = bus.stream("r1")
    asyncio.create_task(bus.publish("a", 1))
    asyncio.create_task(bus.publish("b", 2))

    msgs = await collect(gen1, 2)
    assert len(msgs) == 2

    # first stream is still running; but second one subscribes again
    gen2 = bus.stream("r1")
    asyncio.create_task(bus.publish("c", 3))
    msgs2 = await collect(gen2, 1)
    assert len(msgs2) == 1


async def test_stream_cleanup_on_cancel(bus):
    """Cancelling a stream consumer unsubscribes the client."""
    async def consume():
        async for _ in bus.stream("cancel_me"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    q = await bus.subscribe("cancel_me")
    assert q.empty()


async def test_stream_delivers_published_events(bus):
    """Stream delivers published events as SSE-formatted strings."""
    gen = bus.stream("stest")
    asyncio.create_task(bus.publish("hello", "world"))
    ev = await asyncio.wait_for(gen.__anext__(), timeout=2)
    lines = ev.strip().split("\n")
    data_line = next(l for l in lines if l.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed == {"type": "hello", "data": "world"}


# ── 8. Edge cases ────────────────────────────────────────────────────────


async def test_empty_event_data(bus):
    q = await bus.subscribe("empty")
    await bus.publish("empty", "")
    ev = await asyncio.wait_for(q.get(), timeout=1)
    assert ev == {"type": "empty", "data": ""}


async def test_large_payload(bus):
    large = "x" * 100_000
    q = await bus.subscribe("large")
    await bus.publish("big", large)
    ev = await asyncio.wait_for(q.get(), timeout=2)
    assert ev["data"] == large
    assert len(json.dumps(ev)) > 100_000


async def test_special_characters_in_data(bus):
    special = "héllo wörld 🎉 <tag> & \"quotes\""
    q = await bus.subscribe("special")
    await bus.publish("chars", special)
    ev = await asyncio.wait_for(q.get(), timeout=1)
    assert ev == {"type": "chars", "data": special}


async def test_none_data(bus):
    q = await bus.subscribe("none_data")
    await bus.publish("nullish", None)
    ev = await asyncio.wait_for(q.get(), timeout=1)
    assert ev == {"type": "nullish", "data": None}


async def test_binary_safe_data(bus):
    data = {"bytes": [0, 255, 128]}
    q = await bus.subscribe("bin")
    await bus.publish("binary", data)
    ev = await asyncio.wait_for(q.get(), timeout=1)
    assert ev == {"type": "binary", "data": data}


# ── 9. Event order preservation ──────────────────────────────────────────


async def test_event_order_preserved_per_client(bus):
    q = await bus.subscribe("ordered")
    n = 50
    for i in range(n):
        await bus.publish("num", i)
    received = []
    for _ in range(n):
        ev = await asyncio.wait_for(q.get(), timeout=2)
        received.append(ev["data"])
    assert received == list(range(n))


# ── 10. Queue overflow drops client ──────────────────────────────────────


async def test_queue_full_drops_slow_client(bus):
    q = await bus.subscribe("slow")
    for i in range(200):
        try:
            q.put_nowait({"type": "stale", "data": i})
        except asyncio.QueueFull:
            break
    await bus.publish("fresh", "data")
    assert not q.empty()


# ── 11. Singleton get_event_bus ──────────────────────────────────────────


class TestGetEventBus:
    async def test_singleton_returns_same_instance(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    async def test_singleton_is_eventbus_instance(self):
        assert isinstance(get_event_bus(), EventBus)


# ── 12. Cleanup on shutdown — unsubscribe called via stream ──────────────


async def test_stream_cleanup_on_shutdown(bus):
    """When all stream consumers are cancelled, no remaining subscriptions."""
    tasks = []
    for i in range(5):
        async def consume(cid):
            async for _ in bus.stream(cid):
                break
        tasks.append(asyncio.create_task(consume(f"cleanup{i}")))

    await asyncio.sleep(0.05)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0.05)

    assert len(bus._queues) == 0
