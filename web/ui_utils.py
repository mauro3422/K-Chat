import html

def _match_tools_to_msgs(msgs, all_tools):
    """Asocia tool_calls a mensajes assistant por orden cronológico (single-pass)."""
    msg_tools = {}
    sorted_tools = sorted(all_tools, key=lambda t: t[3])
    assistant_indices = [i for i, (r, *_) in enumerate(msgs) if r == "assistant"]
    tool_ptr = 0
    for msg_idx in assistant_indices:
        _, _, _, ts, _, _ = msgs[msg_idx]
        matched = []
        while tool_ptr < len(sorted_tools):
            t = sorted_tools[tool_ptr]
            if t[3] <= ts:
                matched.append(t)
                tool_ptr += 1
            else:
                break
        msg_tools[ts] = matched
    return msg_tools

def _render_msg_with_phases(role, content, reasoning, matched_tools, ts=None, phases=None):
    parts = []
    label = "Tu" if role == "user" else "Kairos"
    parts.append(f'<div class="msg {role}">')
    parts.append(f'<div class="msg-label">{label}</div>')

    if role == "assistant" and phases:
        tools_by_turn = {}
        for t in matched_tools:
            name, inp, status, t_ts, turn = t
            tools_by_turn.setdefault(turn, []).append((name, status))
        
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
            turn_tools = tools_by_turn.pop(idx + 1, [])
            if turn_tools:
                parts.append('<div class="tool-calls">')
                for name, status in turn_tools:
                    icon = "&#10003;" if status == "ok" else "&#10007;"
                    cls = "tc-item " + status
                    parts.append(f'<span class="{cls}">{icon} {html.escape(name)}</span>')
                parts.append('</div>')
            
            if has_any_phase_content:
                p_content = phase.get("content", "")
                if p_content:
                    body_cls = 'msg-body md-content'
                    parts.append(f'<div class="{body_cls}">{html.escape(p_content)}</div>')
        
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
        if role == "assistant" and matched_tools:
            parts.append('<div class="tool-calls">')
            for name, inp, status, t_ts, turn in matched_tools:
                icon = "&#10003;" if status == "ok" else "&#10007;"
                cls = "tc-item " + status
                parts.append(f'<span class="{cls}">{icon} {html.escape(name)}</span>')
            parts.append('</div>')

        body_cls = 'msg-body md-content' if role == 'assistant' else 'msg-body'
        parts.append(f'<div class="{body_cls}">{html.escape(content)}</div>')

    parts.append(f'<div class="msg-ts">{str(ts)[:16]}</div>')
    parts.append('</div>')
    return "\n".join(parts)
