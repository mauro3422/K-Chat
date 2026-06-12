from src.context import build_system_prompt
from src.llm.client import chat as _llm_chat, chat_stream as _llm_stream
from src.tools.loader import TOOL_MAP as TOOL_MAP

def llm_chat(*args, **kwargs):
    return _llm_chat(*args, build_prompt_fn=build_system_prompt, **kwargs)


def llm_stream(*args, **kwargs):
    return _llm_stream(*args, build_prompt_fn=build_system_prompt, **kwargs)
