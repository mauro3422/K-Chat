import logging
import sys
import asyncio
from typing import Any

from src.api import (
    chat_stream,
    generate_session_id,
    get_default_model,
    OrchestratorDeps,
    get_repos,
)
from src.api.orchestrator import (
    HistoryService,
    LLMService,
    ToolExecutionService,
    TelemetryService,
)
from src.api.repos import init_db, MessageRecord
from src.cli_commands import handle_command

logger: logging.Logger = logging.getLogger(__name__)
SALIR: tuple[str, ...] = ("salir", "exit", "quit", "/salir", "/exit", "chau", "bye")

async def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
    model: str = get_default_model()
    init_db()
    session_id: str = generate_session_id()
    print("Kairos CLI")
    print("Escribí 'salir' para terminar.\n")

    history: list[dict[str, Any]] = []

    # Instantiate services
    repos = get_repos()
    telemetry_service = TelemetryService()
    history_service = HistoryService(repos=repos)
    llm_service = LLMService(telemetry_service=telemetry_service)
    tool_service = ToolExecutionService()
    deps = OrchestratorDeps(
        repos=repos,
        history_service=history_service,
        llm_service=llm_service,
        tool_service=tool_service,
        telemetry_service=telemetry_service,
        session_id=session_id
    )

    while True:
        try:
            entry: str = (await asyncio.to_thread(input, "Tu> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChau.")
            break

        if not entry:
            continue

        if entry.lower() in SALIR:
            print("Chau.")
            break
        if entry.startswith("/"):
            new: str | None = handle_command(entry, history)
            if new:
                model = new
            continue
        try:
            respuesta: str = ""
            primero: bool = True
            async for token in chat_stream(entry, history, model, deps=deps):
                if primero:
                    print("Kairos> ", end="", flush=True)
                    primero = False
                print(token, end="", flush=True)
                respuesta += token
            print("\n")

            await repos.messages.save_record(MessageRecord(session_id=session_id, role="user", content=entry, model="kairos"))
            await repos.messages.save_record(MessageRecord(session_id=session_id, role="assistant", content=respuesta, model="kairos"))
        except Exception as e:
            logger.error("Error en chat_stream: %s", e)

if __name__ == "__main__":
    asyncio.run(main())
