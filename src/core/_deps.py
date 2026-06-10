import functools
from src.context import build_system_prompt
from src.llm.client import chat as _llm_chat, chat_stream as _llm_stream
from src.tools.loader import TOOL_MAP as TOOL_MAP

llm_chat = functools.partial(_llm_chat, build_prompt_fn=build_system_prompt)
llm_stream = functools.partial(_llm_stream, build_prompt_fn=build_system_prompt)


def _lazy_save_message(*args, **kwargs):
    from src.api.messages import save_message
    return save_message(*args, **kwargs)

save_message = _lazy_save_message
