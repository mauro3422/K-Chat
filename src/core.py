import logging
import json
from src.llm import chat as llm_chat, chat_stream as llm_stream, get_default_model
from src.tools import TOOLS, TOOL_MAP
from src.context import build_system_prompt, USER_LANG
from src.compressor import compress_history, should_compress
from src.memory import check_should_rename
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
    phases_output: list = None,
    streaming: bool = True
):
    """Igual que chat() pero yield tokens. history debe ser una lista mutable.
       Si tagged=True, yield (tipo, token): ("reasoning", ...) o ("content", ...).
       Si debug se pasa (dict), se llena con info de depuracion.
       Si phases_output se pasa (list), se llena con [{reasoning, tool_ids}, ...] por fase.
       Si streaming=False usa llm_chat síncrono (modo tests)."""
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

    for event in _run_tool_loop(
        history, model, session_id, tagged, debug, phases_output, used_tools, tool_detail,
        streaming=streaming
    ):
        yield event

    if debug is not None:
        debug["history_before"] = [_msg_snapshot(m) for m in history]
        debug["phases"] = json.dumps(phases_output) if phases_output else "[]"

    if should_compress(history):
        try:
            compress_history(history, model)
        except Exception as e:
            logger.warning("compress_history falló, historial no comprimido: %s", e)


def _run_tool_loop(
    history: list,
    model: str,
    session_id: str,
    tagged: bool,
    debug: dict,
    phases_output: list,
    used_tools: list,
    tool_detail: list,
    streaming: bool = True
):
    """Tool loop unificado. streaming=True usa llm_stream (producción), streaming=False usa llm_chat (tests)."""
    turn = 0
    phase_reasoning = ""
    phase_tool_ids = []
    total_reasoning = []

    MAX_TOOL_TURNS = 5  # Evita loops infinitos si el modelo no resuelve sus errores

    if streaming:
        # --- Path streaming real ---
        while turn < MAX_TOOL_TURNS:
            reasoning_out = []
            tool_calls_out = []
            stream_iter = llm_stream(history, model, reasoning_output=reasoning_out, tagged=True, tools=TOOLS, tool_calls_output=tool_calls_out, debug=debug)

            accumulated = []

            try:
                for tipo, token in stream_iter:
                    accumulated.append((tipo, token))
                    if tipo == "reasoning":
                        total_reasoning.append(token)
                        phase_reasoning += token
                    if tagged:
                        yield (tipo, token)
                    elif tipo == "content":
                        yield token
            except Exception as e:
                logger.warning("Error leyendo del stream: %s", e)

            has_tool_call = bool(tool_calls_out)

            if has_tool_call:
                turn += 1
                assistant_content = "".join(
                    t[1] for t in accumulated if t[0] == "content"
                ) or None
                history.append({
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls_out
                    ],
                })

                for event in run_parallel_tools(
                    tool_calls_out, session_id, turn, history, tool_detail,
                    used_tools, phase_tool_ids, tagged=tagged, tool_map=TOOL_MAP
                ):
                    yield event

                if phases_output is not None:
                    phases_output.append({
                        "reasoning": phase_reasoning,
                        "tool_ids": list(phase_tool_ids),
                        "content": assistant_content or ""
                    })
                phase_reasoning = ""
                phase_tool_ids = []
                continue
            else:
                if phases_output is not None:
                    final_content = "".join(
                        t[1] for t in accumulated if t[0] == "content"
                    ) or ""
                    if phase_reasoning or final_content:
                        phases_output.append({
                            "reasoning": phase_reasoning,
                            "tool_ids": [],
                            "content": final_content
                        })
                break
    else:
        # --- Path síncrono (tests) ---
        result = llm_chat(history, model, tools=TOOLS, debug=debug)
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

            for event in run_parallel_tools(
                tool_calls, session_id, turn, history, tool_detail,
                used_tools, phase_tool_ids, tagged=tagged, tool_map=TOOL_MAP
            ):
                yield event

            if phases_output is not None:
                phases_output.append({
                    "reasoning": phase_reasoning,
                    "tool_ids": list(phase_tool_ids),
                    "content": result.message.content or ""
                })
            phase_reasoning = ""
            phase_tool_ids = []
            result = llm_chat(history, model, tools=TOOLS)

        if used_tools:
            logger.info("Usando: %s", ", ".join(used_tools))

        final_reasoning = getattr(result.message, 'reasoning_content', None) or ""
        if result.message.content:
            full = result.message.content
            if final_reasoning and tagged:
                yield ("reasoning", final_reasoning)
                if phases_output is not None:
                    phases_output.append({
                        "reasoning": final_reasoning,
                        "tool_ids": [],
                        "content": full
                    })
            chunk_size = 12
            for i in range(0, len(full), chunk_size):
                token = full[i:i + chunk_size]
                if tagged:
                    yield ("content", token)
                else:
                    yield token
        else:
            reasoning_out = []
            for item in llm_stream(history, model, reasoning_output=reasoning_out, tagged=tagged):
                if tagged:
                    tipo, token = item
                    yield (tipo, token)
                else:
                    yield item
            final_reasoning = "".join(reasoning_out)

    if debug is not None:
        debug["tool_calls"] = tool_detail
        debug["reasoning"] = "".join(total_reasoning) if streaming else final_reasoning
