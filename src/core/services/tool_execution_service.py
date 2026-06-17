from typing import Any, Generator, Callable, AsyncGenerator
from src.core.services.protocols import ToolExecutionServiceProtocol
from src.core.tool_loop import ToolLoopProtocol, run_tool_loop_streaming, run_tool_loop_sync
from src.tools.runner import run_parallel_tools
from src.tools.registry import ToolRegistryProtocol
from src.context.runtime import invalidate_context_cache
import src.tools as tools

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.core.services.protocols import TelemetryServiceProtocol


def _wrap_run_with_cache_invalidation() -> Callable[..., AsyncGenerator[Any, None]]:
    """Wrap run_parallel_tools to inject invalidate_cache_fn into tool kwargs.

    This breaks the tools→context cycle: instead of save_memory importing
    invalidate_context_cache directly, the Core layer (which sits above both
    tools and context) bridges them.
    """
    async def _run_with_inv(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        async for event in run_parallel_tools(*args, **kwargs, invalidate_cache_fn=invalidate_context_cache):
            yield event
    return _run_with_inv


class ToolExecutionService(ToolExecutionServiceProtocol):
    def __init__(self, tool_registry: ToolRegistryProtocol | None = None, telemetry_service: 'TelemetryServiceProtocol | None' = None):
        self.tool_registry = tool_registry or tools.get_default_registry()
        self.telemetry_service = telemetry_service

    async def execute(
        self,
        history: list[dict[str, Any]],
        model: str,
        session_id: str | None = None,
        tagged: bool = False,
        debug: Any = None,
        phases_output: list[dict[str, Any]] | None = None,
        streaming: bool = True,
        repos: Any = None,
        llm_chat_fn: Callable[..., Any] | None = None,
        llm_chat_stream_fn: Callable[..., Any] | None = None,
    ) -> AsyncGenerator[Any, None]:
        used_tools: list[str] = []
        tool_detail: list[dict[str, Any]] = []

        run_fn = _wrap_run_with_cache_invalidation()
        loop_fn: ToolLoopProtocol = run_tool_loop_streaming if streaming else run_tool_loop_sync
        async for event in loop_fn(
            history, model, session_id, tagged, debug, phases_output,
            used_tools, tool_detail, run_fn, self.tool_registry.tool_map,
            repos=repos,
            llm_chat_fn=llm_chat_fn,
            llm_chat_stream_fn=llm_chat_stream_fn,
            tool_defs=self.tool_registry.tools_openai,
            skill_registry=self.tool_registry._skill_registry,
        ):
            yield event
