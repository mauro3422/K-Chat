from dataclasses import dataclass


@dataclass
class MessageRecord:
    session_id: str = ""
    role: str = ""
    content: str = ""
    model: str | None = None
    reasoning: str = ""
    phases: str = "[]"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tool_calls: str | None = None
    tool_call_id: str | None = None
