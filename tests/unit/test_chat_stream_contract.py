import pytest
from unittest.mock import MagicMock, AsyncMock

from web.services.chat_stream import build_stream_generator
from web.services.chat_stream_contract import StreamGeneratorDeps


@pytest.mark.anyio
async def test_stream_generator_deps_defaults_are_empty():
    deps = StreamGeneratorDeps()

    assert deps.chat_stream_fn is None
    assert deps.loop_detector is None
    assert deps.retry_handler is None
    assert deps.save_fn is None
    assert deps.rename_fn is None


@pytest.mark.anyio
async def test_build_stream_generator_uses_dependency_bundle():
    async def mock_chat_stream(*args, **kwargs):
        yield ("content", "hola")

    deps = StreamGeneratorDeps(
        chat_stream_fn=mock_chat_stream,
        save_fn=AsyncMock(),
        rename_fn=AsyncMock(),
    )

    bg = MagicMock()
    bg.add_task = MagicMock()
    gen_fn = build_stream_generator("ses-1", "Hola", [{"role": "system", "content": "test"}], "m", bg, deps=deps)

    chunks = [t async for t in gen_fn()]

    assert chunks[0].strip() == '{"t": "content", "d": "hola"}'
