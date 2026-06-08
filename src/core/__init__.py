import sys
from types import ModuleType

from src.core.orchestrator import chat, chat_stream
from src.llm import get_default_model
from src.context import build_system_prompt

class CoreModule(ModuleType):
    @property
    def llm_chat(self):
        val = getattr(self, '_llm_chat_mock', None)
        if val is not None:
            return val
        import src.llm
        return src.llm.chat

    @llm_chat.setter
    def llm_chat(self, value):
        self._llm_chat_mock = value

    @llm_chat.deleter
    def llm_chat(self):
        if hasattr(self, '_llm_chat_mock'):
            del self._llm_chat_mock

    @property
    def llm_stream(self):
        val = getattr(self, '_llm_stream_mock', None)
        if val is not None:
            return val
        import src.llm
        return src.llm.chat_stream

    @llm_stream.setter
    def llm_stream(self, value):
        self._llm_stream_mock = value

    @llm_stream.deleter
    def llm_stream(self):
        if hasattr(self, '_llm_stream_mock'):
            del self._llm_stream_mock

    @property
    def TOOL_MAP(self):
        val = getattr(self, '_TOOL_MAP_mock', None)
        if val is not None:
            return val
        import src.tools
        return src.tools.TOOL_MAP

    @TOOL_MAP.setter
    def TOOL_MAP(self, value):
        self._TOOL_MAP_mock = value

    @TOOL_MAP.deleter
    def TOOL_MAP(self):
        if hasattr(self, '_TOOL_MAP_mock'):
            del self._TOOL_MAP_mock

sys.modules[__name__].__class__ = CoreModule
