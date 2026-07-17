from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from web.app_factory import (
    _bounded_retry_delay,
    _run_node_failover_iteration,
    _run_node_heartbeat_iteration,
    _run_resilient_periodic_task,
)


def test_retry_delay_is_exponential_and_bounded():
    assert _bounded_retry_delay(1, minimum_seconds=0.1, maximum_seconds=0.4) == 0.1
    assert _bounded_retry_delay(2, minimum_seconds=0.1, maximum_seconds=0.4) == 0.2
    assert _bounded_retry_delay(20, minimum_seconds=0.1, maximum_seconds=0.4) == 0.4


@pytest.mark.anyio
async def test_heartbeat_loop_recovers_after_iteration_failure(caplog):
    recovered = asyncio.Event()
    attempts = 0

    async def broadcast_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary heartbeat failure")
        recovered.set()

    app = SimpleNamespace(
        state=SimpleNamespace(node_bridge=SimpleNamespace(broadcast_once=broadcast_once))
    )
    caplog.set_level(logging.WARNING, logger="web.app_factory")
    task = asyncio.create_task(
        _run_resilient_periodic_task(
            lambda: _run_node_heartbeat_iteration(app),
            task_name="Node LAN heartbeat",
            interval_seconds=0.05,
            run_immediately=True,
            retry_minimum_seconds=0.05,
            retry_maximum_seconds=0.1,
        )
    )

    await asyncio.wait_for(recovered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert attempts == 2
    assert "consecutive_failures=1" in caplog.text
    assert "temporary heartbeat failure" in caplog.text


@pytest.mark.anyio
async def test_failover_loop_recovers_after_iteration_failure(caplog):
    recovered = asyncio.Event()
    attempts = 0

    async def is_primary() -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary coordinator failure")
        return True

    failover_state = SimpleNamespace(
        reset=lambda reason: recovered.set(),
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            node_coordinator=SimpleNamespace(is_primary=is_primary),
            failover_state=failover_state,
        )
    )
    caplog.set_level(logging.WARNING, logger="web.app_factory")
    task = asyncio.create_task(
        _run_resilient_periodic_task(
            lambda: _run_node_failover_iteration(app, ttl=0.2),
            task_name="Node failover monitor",
            interval_seconds=0.05,
            run_immediately=True,
            retry_minimum_seconds=0.05,
            retry_maximum_seconds=0.1,
        )
    )

    await asyncio.wait_for(recovered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert attempts == 2
    assert "consecutive_failures=1" in caplog.text
    assert "temporary coordinator failure" in caplog.text


@pytest.mark.anyio
async def test_periodic_task_propagates_cancellation_from_iteration(caplog):
    started = asyncio.Event()

    async def blocked_iteration() -> None:
        started.set()
        await asyncio.Event().wait()

    caplog.set_level(logging.WARNING, logger="web.app_factory")
    task = asyncio.create_task(
        _run_resilient_periodic_task(
            blocked_iteration,
            task_name="Node LAN heartbeat",
            interval_seconds=0.05,
            run_immediately=True,
        )
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "iteration failed" not in caplog.text
