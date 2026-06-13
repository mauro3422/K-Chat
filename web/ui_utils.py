import html
from typing import Any

def render_msg_with_phases(role: str, content: str, reasoning: str, matched_tools: list[dict[str, Any]], ts: Any | None = None, phases: list[dict[str, Any]] | None = None) -> str:
    parts = []
    label = "Tu" if role == "user" else "Kairos"
    parts.append(f'<div class="msg {role}">')
    parts.append(f'<div class="msg-label">{label}</div>')

    if role == "assistant" and phases:
        tools_by_turn = {}
        for t in matched_tools:
            turn = t.get("turn", 0)
            tools_by_turn.setdefault(turn, []).append((t["tool_name"], t["status"]))

        has_any_phase_content = any(phase.get("content") for phase in phases)

        for idx, phase in enumerate(phases):
            r_text = phase.get("reasoning", "")
            if r_text:
                parts.append(
                    '<details class="reasoning" open>'
                    '<summary>Razonamiento</summary>'
                    f'<div class="rt">{html.escape(r_text)}</div>'
                    '</details>'
                )
            if has_any_phase_content:
                p_content = phase.get("content", "")
                if p_content:
                    body_cls = 'msg-body md-content'
                    parts.append(f'<div class="{body_cls}">{html.escape(p_content)}</div>')

            turn_tools = tools_by_turn.pop(idx + 1, [])
            if turn_tools:
                parts.append('<div class="tool-calls">')
                for name, status in turn_tools:
                    icon = "&#10003;" if status == "ok" else "&#10007;"
                    cls = "tc-item " + status
                    parts.append(f'<span class="{cls}">{icon} {html.escape(name)}</span>')
                parts.append('</div>')

        if not has_any_phase_content:
            body_cls = 'msg-body md-content'
            parts.append(f'<div class="{body_cls}">{html.escape(content)}</div>')
    else:
        if reasoning:
            parts.append(
                '<details class="reasoning" open>'
                '<summary>Razonamiento</summary>'
                f'<div class="rt">{html.escape(reasoning)}</div>'
                '</details>'
            )

        body_cls = 'msg-body md-content' if role == 'assistant' else 'msg-body'
        parts.append(f'<div class="{body_cls}">{html.escape(content)}</div>')

        if role == "assistant" and matched_tools:
            parts.append('<div class="tool-calls">')
            for t in matched_tools:
                icon = "&#10003;" if t["status"] == "ok" else "&#10007;"
                cls = "tc-item " + t["status"]
                parts.append(f'<span class="{cls}">{icon} {html.escape(t["tool_name"])}</span>')
            parts.append('</div>')

    parts.append(f'<div class="msg-ts">{str(ts)[:16]}</div>')
    parts.append('</div>')
    return "\n".join(parts)
