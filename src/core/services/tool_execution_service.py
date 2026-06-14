from typing import Any, Generator, Callable, AsyncGenerator
from src.core.tool_loop import run_tool_loop_streaming, run_tool_loop_sync
from src.tools.runner import run_parallel_tools
from src.tools.registry import ToolRegistry
import src.tools as tools

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.core.services.telemetry_service import TelemetryService

class ToolExecutionService:
    def __init__(self, tool_registry: ToolRegistry | None = None, telemetry_service: 'TelemetryService | None' = None):
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

        loop_fn = run_tool_loop_streaming if streaming else run_tool_loop_sync
        async for event in loop_fn(
            history, model, session_id, tagged, debug, phases_output,
            used_tools, tool_detail, run_parallel_tools, self.tool_registry.tool_map,
            repos=repos,
            llm_chat_fn=llm_chat_fn,
            llm_chat_stream_fn=llm_chat_stream_fn,
            tool_defs=self.tool_registry.tools_openai,
        ):
            yield event
