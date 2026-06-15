"""Tests for the Telegram message manager — phase & message ID tracking."""

from __future__ import annotations

import pytest

from channels.telegram.message_manager import MessageManager


@pytest.mark.asyncio
async def test_get_set_msg_id():
    mm = MessageManager()
    await mm.set_msg_id(123, "reasoning", 0, 1001)
    assert mm.get_msg_id(123, "reasoning", 0) == 1001


@pytest.mark.asyncio
async def test_get_nonexistent_msg_id():
    mm = MessageManager()
    assert mm.get_msg_id(999, "reasoning", 0) is None


@pytest.mark.asyncio
async def test_has_phase_true():
    mm = MessageManager()
    await mm.set_msg_id(123, "content", 0, 2001)
    assert mm.has_phase(123, "content", 0) is True


@pytest.mark.asyncio
async def test_has_phase_false():
    mm = MessageManager()
    assert mm.has_phase(456, "reasoning", 5) is False


@pytest.mark.asyncio
async def test_multiple_chats_isolated():
    mm = MessageManager()
    await mm.set_msg_id(111, "reasoning", 0, 100)
    await mm.set_msg_id(222, "reasoning", 0, 200)
    assert mm.get_msg_id(111, "reasoning", 0) == 100
    assert mm.get_msg_id(222, "reasoning", 0) == 200


@pytest.mark.asyncio
async def test_multiple_phases_same_chat():
    mm = MessageManager()
    await mm.set_msg_id(123, "reasoning", 0, 1001)
    await mm.set_msg_id(123, "content", 0, 2001)
    await mm.set_msg_id(123, "reasoning", 1, 1002)
    await mm.set_msg_id(123, "content", 1, 2002)

    assert mm.get_msg_id(123, "reasoning", 0) == 1001
    assert mm.get_msg_id(123, "content", 0) == 2001
    assert mm.get_msg_id(123, "reasoning", 1) == 1002
    assert mm.get_msg_id(123, "content", 1) == 2002


@pytest.mark.asyncio
async def test_reset_phases_clears_reasoning_and_content():
    mm = MessageManager()
    await mm.set_msg_id(123, "reasoning", 0, 1001)
    await mm.set_msg_id(123, "content", 0, 2001)
    await mm.set_tool_msg_id(123, "call_x", 3001)

    await mm.reset_phases(123)

    assert mm.get_msg_id(123, "reasoning", 0) is None
    assert mm.get_msg_id(123, "content", 0) is None
    assert mm.get_tool_msg_id(123, "call_x") == 3001


@pytest.mark.asyncio
async def test_reset_phases_then_new_phase():
    mm = MessageManager()
    await mm.set_msg_id(123, "reasoning", 0, 1001)
    await mm.reset_phases(123)
    assert mm.get_msg_id(123, "reasoning", 0) is None


@pytest.mark.asyncio
async def test_tool_messages():
    mm = MessageManager()
    await mm.set_tool_msg_id(123, "call_abc", 4001)
    assert mm.get_tool_msg_id(123, "call_abc") == 4001
    assert mm.get_tool_msg_id(123, "call_xyz") is None


@pytest.mark.asyncio
async def test_cleanup_removes_all():
    mm = MessageManager()
    await mm.set_msg_id(123, "reasoning", 0, 1001)
    await mm.set_tool_msg_id(123, "call_x", 3001)
    await mm.cleanup(123)
    assert mm.get_msg_id(123, "reasoning", 0) is None
    assert mm.get_tool_msg_id(123, "call_x") is None


@pytest.mark.asyncio
async def test_get_all_msg_ids_includes_all():
    mm = MessageManager()
    await mm.set_msg_id(123, "reasoning", 0, 1001)
    await mm.set_msg_id(123, "content", 0, 2001)
    await mm.set_tool_msg_id(123, "call_x", 3001)
    ids = await mm.get_all_msg_ids(123)
    assert sorted(ids) == [1001, 2001, 3001]


@pytest.mark.asyncio
async def test_get_all_msg_ids_empty_chat():
    mm = MessageManager()
    ids = await mm.get_all_msg_ids(999)
    assert ids == []
