import sys
import uuid
from src.core import chat_stream
from src.memory import init_db, save_message
from src.handler_cli import handle_command
from src.core import get_default_model
SALIR = ("salir", "exit", "quit", "/salir", "/exit", "chau", "bye")

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    model= get_default_model()
    init_db()
    session_id = str(uuid.uuid4())
    print("Kairos CLI")
    print("Escribí 'salir' para terminar.\n")

    history = []


    while True:
        try:
            entry = input("Tu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nChau.")
            break

        if not entry:
            continue

        if entry.lower() in SALIR:
            print("Chau.")
            break
        if entry.startswith("/"):
            new=handle_command(entry, history)
            if new:
                model = new
            continue
        try:
            respuesta = ""
            primero = True
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
            print(f"\nError: {e}\n")

if __name__ == "__main__":
    main()
