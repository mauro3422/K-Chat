import sys
from types import ModuleType

from src.llm.client import chat, chat_stream
from src.llm.models import (
    PRIORITY,
    FALLBACK_MODEL,
    _failed_models,
    _api_call,
    _switch_model,
    _update_system_prompt
)
from src.llm.manager import (
    verify_model,
    get_verified_models,
    get_models,
    get_free_models,
    get_paid_models,
    get_default_model,
    _mark_and_refresh
)

class LLMModule(ModuleType):
    @property
    def client(self):
        from src.llm import models
        return models.client

    @client.setter
    def client(self, value):
        from src.llm import models
        models.client = value

sys.modules[__name__].__class__ = LLMModule
