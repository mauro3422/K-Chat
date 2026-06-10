import logging
import sys
from typing import Any
from src.api import chat_stream, get_default_model, init_db, generate_session_id, save_message
from src.handler_cli import handle_command

logger: logging.Logger = logging.getLogger(__name__)
SALIR: tuple[str, ...] = ("salir", "exit", "quit", "/salir", "/exit", "chau", "bye")

def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
    model: str = get_default_model()
    init_db()
    session_id: str = generate_session_id()
    print("Kairos CLI")
    print("Escribí 'salir' para terminar.\n")

    history: list[dict[str, Any]] = []


    while True:
        try:
            entry: str = input("Tu> ").strip()
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
            for token in chat_stream(entry, history, model, session_id=session_id):
                if primero:
                    print("Kairos> ", end="", flush=True)
                    primero = False
                print(token, end="", flush=True)
                respuesta += token
            print("\n")

            save_message(session_id, "user", entry, "kairos")
            save_message(session_id, "assistant", respuesta, "kairos")
        except Exception as e:
            logger.error("Error en chat_stream: %s", e)

if __name__ == "__main__":
    main()
