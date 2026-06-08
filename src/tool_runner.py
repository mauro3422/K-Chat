import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)
from src.tools import TOOL_MAP, TOOLS
from src.memory import log_tool_call


def _get_required_params(tool_name: str) -> list:
    """Obtiene los parámetros requeridos de un tool desde su DEFINITION."""
    for t in TOOLS:
        if t.get("function", {}).get("name") == tool_name:
            return t.get("function", {}).get("parameters", {}).get("required", [])
    return []


def run_parallel_tools(
    tool_calls: list,
    session_id: str,
    turn: int,
    history: list,
    tool_detail: list,
    used_tools: list,
    phase_tool_ids: list,
    tagged: bool = False,
    tool_map: dict = None
):
    """Ejecuta un lote de tool_calls en paralelo y yielding eventos de streaming si tagged=True."""
    if tool_map is None:
        tool_map = TOOL_MAP

    tcs_info = []
    for tc in tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments
        logger.debug("tool_runner RECV: name=%r id=%r arguments=%r", name, tc.id, raw_args)
        try:
            args = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("tool_runner: JSON inválido en tool_call '%s' (%s): repr=%r error=%s", name, tc.id, raw_args, e)
            args = {}
        # Validar si el tool es válido y existe en el mapa
        if not name or name.startswith("$") or name not in tool_map:
            tool_result = f"[ERROR]: El tool '{name}' no existe o no es válido."
            status = "error"
            if tagged:
                yield ("tool_call", json.dumps({"id": tc.id, "name": name or "unknown", "status": "calling"}))
                yield ("tool_call", json.dumps({"id": tc.id, "name": name or "unknown", "status": status}))
            if session_id:
                log_tool_call(session_id, name or "unknown", json.dumps(args, ensure_ascii=False), status, turn=turn)
            history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})
            tool_detail.append({"name": name or "unknown", "args": args, "status": status, "result_truncated": tool_result[:300]})
            continue

        if name not in used_tools:
            used_tools.append(name)

        required = _get_required_params(name)
        missing = [p for p in required if p not in args or not str(args[p]).strip()]
        if missing:
            tool_result = f"[ERROR en {name}]: Faltan parámetros requeridos: {', '.join(missing)}. Debes proporcionar todos los parámetros obligatorios."
            status = "error"
            if tagged:
                # Emitir 'calling' primero para que la UI tenga el span, luego 'error'
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": "calling"}))
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": status}))
            if session_id:
                log_tool_call(session_id, name, json.dumps(args, ensure_ascii=False), status, turn=turn)
            history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})
            tool_detail.append({"name": name, "args": args, "status": status, "result_truncated": tool_result[:300]})
            continue

        tcs_info.append((tc, name, args))
        if tagged:
            yield ("tool_call", json.dumps({"id": tc.id, "name": name, "args": args, "status": "calling"}))
            phase_tool_ids.append(tc.id)

    results = {}
    with ThreadPoolExecutor(max_workers=max(1, len(tcs_info))) as pool:
        futs = {}
        for tc, name, args in tcs_info:
            futs[pool.submit(tool_map[name], **args, _session_id=session_id)] = (tc, name)
        for fut in as_completed(futs):
            tc, name = futs[fut]
            try:
                tool_result = fut.result()
                status = "ok"
            except Exception as e:
                tool_result = f"[ERROR en {name}]: {e}"
                status = "error"
            if len(tool_result) > 2000:
                tool_result = tool_result[:2000] + "\n...[truncado]"
            results[tc.id] = (tool_result, status)
            if tagged:
                yield ("tool_call", json.dumps({"id": tc.id, "name": name, "status": status}))

    for tc, name, args in tcs_info:
        tool_result, status = results[tc.id]
        tool_detail.append({
            "name": name,
            "args": args,
            "status": status,
            "result_truncated": tool_result[:300]
        })
        if session_id:
            log_tool_call(session_id, name, json.dumps(args, ensure_ascii=False), status, turn=turn)
        history.append({"role": "tool", "content": tool_result, "tool_call_id": tc.id})
