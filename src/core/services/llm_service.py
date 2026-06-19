import time
from functools import partial
from typing import Any, AsyncGenerator, Callable
from src.core.services.protocols import LLMServiceProtocol
import src.llm.client as llm_client
from src.llm.selector import get_default_model

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.core.services.protocols import TelemetryServiceProtocol

class LLMService(LLMServiceProtocol):
    def __init__(
        self,
        chat_fn: Callable[..., Any] | None = None,
        chat_stream_fn: Callable[..., Any] | None = None,
        default_model_fn: Callable[[], str] | None = None,
        model_registry: Any | None = None,
        telemetry_service: 'TelemetryServiceProtocol | None' = None
    ):
        self._chat_fn = chat_fn or partial(llm_client.chat, registry=model_registry)
        self._chat_stream_fn = chat_stream_fn or partial(llm_client.chat_stream, registry=model_registry)
        self._default_model_fn = default_model_fn or get_default_model
        self.telemetry_service = telemetry_service

    async def chat(self, messages: list[dict[str, Any]], model: str, **kwargs) -> Any:
        start_time = time.time()
        response = await self._chat_fn(messages, model, **kwargs)
        duration = time.time() - start_time
        
        if self.telemetry_service:
            # Try to extract token usage if available in response
            tokens = 0
            if hasattr(response, 'usage') and response.usage:
                tokens = getattr(response.usage, 'total_tokens', 0)
            elif isinstance(response, dict) and 'usage' in response:
                tokens = response['usage'].get('total_tokens', 0)
            
            self.telemetry_service.track_llm_usage(model, tokens, duration)
            
        return response

    async def chat_stream(self, messages: list[dict[str, Any]], model: str, **kwargs) -> AsyncGenerator[Any, None]:
        # For streaming, it's harder to track total tokens here without wrapping the generator
        # For now, let's at least track the start of the stream or the total duration if we wrap it
        start_time = time.time()
        total_tokens = 0
        try:
            async for chunk in self._chat_stream_fn(messages, model, **kwargs):
                # Some clients might provide usage in chunks
                if hasattr(chunk, 'usage') and chunk.usage:
                    total_tokens = getattr(chunk.usage, 'total_tokens', total_tokens)
                yield chunk
        finally:
            duration = time.time() - start_time
            if self.telemetry_service:
                self.telemetry_service.track_llm_usage(model, total_tokens, duration)

    def get_default_model(self) -> str:
        return self._default_model_fn()
