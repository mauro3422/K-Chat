from __future__ import annotations

from web.services.codex_task_bridge import create_task, get_task, list_tasks, update_task


def test_codex_task_bridge_lifecycle(tmp_path):
    path = tmp_path / "tasks.json"

    task = create_task(
        title="Arreglar health remoto",
        prompt="Revisar por que falla /health en la laptop.",
        from_node="laptop",
        session_id="session-1",
        priority="high",
        path=path,
    )

    assert task["id"].startswith("ctx-")
    assert task["status"] == "open"
    assert task["messages"][0]["role"] == "kairos"

    listed = list_tasks(path=path)
    assert [item["id"] for item in listed] == [task["id"]]

    running = update_task(
        task["id"],
        status="running",
        message="Tomado por Codex.",
        claimed_by="codex",
        path=path,
    )
    assert running is not None
    assert running["status"] == "running"
    assert running["claimed_by"] == "codex"
    assert running["messages"][-1]["role"] == "codex"

    done = update_task(task["id"], status="done", message="Listo.", path=path)
    assert done is not None
    assert done["status"] == "done"
    assert get_task(task["id"], path=path)["messages"][-1]["content"] == "Listo."


def test_codex_task_bridge_filters_by_status(tmp_path):
    path = tmp_path / "tasks.json"
    first = create_task(title="Uno", prompt="hacer uno", path=path)
    second = create_task(title="Dos", prompt="hacer dos", path=path)
    update_task(first["id"], status="done", path=path)

    open_tasks = list_tasks(path=path)
    assert [task["id"] for task in open_tasks] == [second["id"]]

    all_tasks = list_tasks(status="all", path=path)
    assert {task["id"] for task in all_tasks} == {first["id"], second["id"]}
