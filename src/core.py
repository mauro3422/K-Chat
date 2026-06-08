import logging
import json
from src.llm import chat as llm_chat, chat_stream as llm_stream, get_default_model
from src.tools import TOOLS, TOOL_MAP
from src.context import build_system_prompt, USER_LANG
from src.compressor import compress_history, MAX_HISTORY
from src.tool_runner import run_parallel_tools

logger = logging.getLogger(__name__)

def _msg_snapshot(m):
    if isinstance(m, dict):
        return {"role": m["role"], "content": (m.get("content") or "")[:500]}
    return {"role": m.role, "content": (m.content or "")[:500]}

def chat(message_user: str, history: list = None) -> tuple[str, list]:
    """Procesa un mensaje con texto y memoria. Devuelve respuesta y historial actualizado."""
    model = get_default_model()
    if history is None:
        history = [build_system_prompt(model)]
    history.append({"role": "user", "content": message_user})
    choice = llm_chat(history, model)
    response = choice.message.content
    history.append({"role": "assistant", "content": response})
    return response, history

def chat_stream(
    message_user: str,
    history: list,
    model: str = None,
    session_id: str = None,
    tagged: bool = False,
    debug: dict = None,
    phases_output: list = None
):
    """Igual que chat() pero yield tokens. history debe ser una lista mutable.
       Si tagged=True, yield (tipo, token): ("reasoning", ...) o ("content", ...).
       Si debug se pasa (dict), se llena con info de depuracion.
       Si phases_output se pasa (list), se llena con [{reasoning, tool_ids}, ...] por fase."""
    if model is None:
        model = get_default_model()

    if phases_output is not None:
        phases_output.clear()

    if debug is not None:
        debug.clear()
        debug["model"] = model
        debug["session_id"] = session_id
        debug["reasoning"] = ""
        debug["tool_calls"] = []
        debug["history_before"] = []
        debug["system_prompt"] = ""

    if len(history) == 0:
        history.append(build_system_prompt(model))

    if debug is not None:
        debug["system_prompt"] = history[0]["content"]

    history.append({"role": "user", "content": message_user})

    if debug is not None:
        debug["history_before"] = [_msg_snapshot(m) for m in history]

    used_tools = []
    tool_detail = []
    turn = 0
    phase_reasoning = ""
    phase_tool_ids = []
    result = llm_chat(history, model, tools=TOOLS)
    while result.finish_reason == "tool_calls":
        turn += 1
        rc = getattr(result.message, 'reasoning_content', None)
        if rc and tagged:
            yield ("reasoning", rc)
            phase_reasoning += rc
        if result.message.content:
            interim = result.message.content
            if tagged:
                yield ("reasoning", interim)
            phase_reasoning += interim

        tool_calls = result.message.tool_calls
        history.append(result.message)

        # Delegar la ejecución paralela de las tools al módulo tool_runner
        for event in run_parallel_tools(
            tool_calls,
            session_id,
            turn,
            history,
            tool_detail,
            used_tools,
            phase_tool_ids,
            tagged=tagged,
            tool_map=TOOL_MAP
        ):
            yield event

        if phases_output is not None and phase_reasoning:
            phases_output.append({"reasoning": phase_reasoning, "tool_ids": list(phase_tool_ids)})
        phase_reasoning = ""
        phase_tool_ids = []
        result = llm_chat(history, model, tools=TOOLS)

    if debug is not None:
        debug["tool_calls"] = tool_detail

    if used_tools:
        logger.info("Usando: %s", ", ".join(used_tools))

    if result.message.content:
        full = result.message.content
        rc = getattr(result.message, 'reasoning_content', None) or ""
        if rc and tagged:
            yield ("reasoning", rc)
            if phases_output is not None:
                phases_output.append({"reasoning": rc, "tool_ids": []})
        chunk_size = 12
        for i in range(0, len(full), chunk_size):
            token = full[i:i + chunk_size]
            if tagged:
                yield ("content", token)
            else:
                yield token
        if debug is not None:
            debug["reasoning"] = rc
    else:
        reasoning_out = []
        for item in llm_stream(history, model, reasoning_output=reasoning_out, tagged=tagged):
            if tagged:
                tipo, token = item
                yield (tipo, token)
            else:
                yield item
        if debug is not None:
            debug["reasoning"] = "".join(reasoning_out)

    if debug is not None:
        debug["history_before"] = [_msg_snapshot(m) for m in history]
        debug["phases"] = json.dumps(phases_output) if phases_output else "[]"

    if len(history) > MAX_HISTORY:
        try:
            compress_history(history, model)
        except Exception as e:
            print(f"[Warn] compress_history falló, historial no comprimido: {e}")
