from web.services.stream_retry_handler import StreamRetryHandler, CONTINUATION_INSTRUCTION


def test_can_retry_starts_true():
    h = StreamRetryHandler(max_retries=2)
    assert h.can_retry is True
    assert h.retry_count == 0


def test_can_retry_false_after_exhaustion():
    h = StreamRetryHandler(max_retries=1)
    h.retry_count = 1
    assert h.can_retry is False


def test_zero_max_retries():
    h = StreamRetryHandler(max_retries=0)
    assert h.can_retry is False


def test_build_messages_adds_assistant_and_continuation():
    h = StreamRetryHandler()
    history = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a poem."},
    ]
    messages = h.build_messages(history, partial_content="Roses are red",
                                 partial_reasoning="")

    assert len(messages) == 4
    assert messages[0] == history[0]
    assert messages[1] == history[1]
    assert messages[2]["role"] == "assistant"
    assert "Roses are red" in messages[2]["content"]
    assert messages[3]["role"] == "user"


def test_build_messages_combines_reasoning_and_content():
    h = StreamRetryHandler()
    history = [{"role": "user", "content": "Explain."}]
    messages = h.build_messages(history,
                                 partial_content="Final answer.",
                                 partial_reasoning="Thinking step 1")

    assert len(messages) == 3
    asst_msg = messages[1]
    assert asst_msg["role"] == "assistant"
    assert "Thinking step 1" in asst_msg["content"]
    assert "Final answer." in asst_msg["content"]


def test_build_messages_appends_continuation_instruction():
    h = StreamRetryHandler()
    messages = h.build_messages([], partial_content="Hello",
                                 partial_reasoning="")
    last = messages[-1]
    assert last["role"] == "user"
    assert last["content"] == CONTINUATION_INSTRUCTION


def test_attempt_recovery_returns_empty_when_exhausted():
    """When max_retries=0, attempt_recovery yields nothing."""
    h = StreamRetryHandler(max_retries=0)
    gen = h.attempt_recovery([], "hi", "", "gpt-4")
    items = list(gen)
    assert items == []
