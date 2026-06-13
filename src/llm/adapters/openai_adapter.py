from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from openai import OpenAI

from src.llm.protocol import (
    LLMProvider,
    UnifiedRequest,
    UnifiedResponse,
    UnifiedStreamEvent,
    UnifiedToolCall,
    UnifiedToolCallDelta,
    Usage,
    FinishInfo,
)

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMProvider):
    def __init__(self, api_key: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supports_streaming(self) -> bool:
        return True

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_reasoning(self) -> bool:
        return True

    def chat(self, request: UnifiedRequest) -> UnifiedResponse:
        openai_messages = self._to_openai_messages(request.messages)
        openai_tools = self._to_openai_tools(request.tools)

        response = self._client.chat.completions.create(
            model=request.model,
            messages=openai_messages,
            tools=openai_tools,
            stream=False,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return self._from_openai_response(response, request.model)

    def chat_stream(self, request: UnifiedRequest) -> Generator[UnifiedStreamEvent, None, None]:
        openai_messages = self._to_openai_messages(request.messages)
        openai_tools = self._to_openai_tools(request.tools)

        stream = self._client.chat.completions.create(
            model=request.model,
            messages=openai_messages,
            tools=openai_tools,
            stream=True,
            stream_options={"include_usage": True},
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        yield from self._parse_openai_stream(stream)

    def list_models(self) -> list[str]:
        return [m.id for m in self._client.models.list()]

    def _to_openai_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for msg in messages:
            m = dict(msg)
            if m.get("tool_calls"):
                m["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in m["tool_calls"]
                ]
            result.append(m)
        return result

    def _to_openai_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        return tools

    def _from_openai_response(self, response: Any, model: str) -> UnifiedResponse:
        msg = response.choices[0].message
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                UnifiedToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in msg.tool_calls
            ]
        return UnifiedResponse(
            content=msg.content,
            reasoning=getattr(msg, "reasoning_content", None),
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ) if response.usage else None,
            finish_reason=response.choices[0].finish_reason,
            model=model,
        )

    def _parse_openai_stream(self, stream) -> Generator[UnifiedStreamEvent, None, None]:
        tool_map: dict[int, UnifiedToolCallDelta] = {}

        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning:
                yield ("reasoning", reasoning)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index or 0
                    if idx not in tool_map:
                        tool_map[idx] = UnifiedToolCallDelta(
                            index=idx, id=None, name=None, arguments="", status="start"
                        )
                    if tc.id:
                        tool_map[idx].id = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_map[idx].name = tc.function.name
                            tool_map[idx].status = "partial"
                        if tc.function.arguments:
                            tool_map[idx].arguments += tc.function.arguments
                            tool_map[idx].status = "partial"
                            yield ("tool_call", UnifiedToolCallDelta(
                                index=idx,
                                id=tool_map[idx].id,
                                name=tool_map[idx].name,
                                arguments=tool_map[idx].arguments,
                                status="partial"
                            ))

            if delta.content:
                yield ("content", delta.content)

            if chunk.usage:
                yield ("usage", Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                ))

        yield ("done", FinishInfo(finish_reason="stop", usage=None))