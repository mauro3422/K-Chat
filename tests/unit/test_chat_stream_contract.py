from unittest.mock import MagicMock

from web.services.chat_stream import build_stream_generator
from web.services.chat_stream_contract import StreamGeneratorDeps


def test_stream_generator_deps_defaults_are_empty():
    deps = StreamGeneratorDeps()

    assert deps.chat_stream_fn is None
    assert deps.loop_detector is None
    assert deps.retry_handler is None
    assert deps.save_fn is None
    assert deps.rename_fn is None


def test_build_stream_generator_uses_dependency_bundle():
    mock_chat_stream = MagicMock(return_value=iter([("content", "hola")]))
    deps = StreamGeneratorDeps(
        chat_stream_fn=mock_chat_stream,
        save_fn=MagicMock(),
        rename_fn=MagicMock(),
    )

    bg = MagicMock()
    bg.add_task = MagicMock()
    gen = build_stream_generator("ses-1", "Hola", [{"role": "system", "content": "test"}], "m", bg, deps=deps)

    chunks = list(gen())

    assert chunks[0].strip() == '{"t": "content", "d": "hola"}'
    mock_chat_stream.assert_called_once()
