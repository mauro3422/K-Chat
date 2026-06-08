import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.tools import TOOL_MAP
from src.memory import log_tool_call

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
        args = json.loads(tc.function.arguments)
        if name not in used_tools:
            used_tools.append(name)
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
