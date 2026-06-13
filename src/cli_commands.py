from typing import Any

from src.llm.selector import get_default_model

def handle_command(entry: str, history: list[dict[str, Any]]) -> str | None:
    """Procesa comandos /. Devuelve un modelo nuevo si se cambió, None si no."""
    parts = entry.strip().split()
    cmd = parts[0].lower()

    if cmd == "/model":
        if len(parts) > 1:
            history.append({"role": "system", "content": f"[User switched model to: {parts[1]}]"})
            print(f"Modelo cambiado a: {parts[1]}")
            return parts[1]
        else:
            print(f"Modelo actual: {get_default_model()}")
            return None

    if cmd == "/clear":
        history.clear()
        print("Historial borrado.")
        return None

    if cmd == "/help":
        print("/model <modelo>   - Cambiar modelo")
        print("/clear            - Limpiar historial")
        print("/exit             - Salir")
        print("/help             - Mostrar ayuda")
        return None

    print(f"Comando desconocido: {cmd}. Usá /help")
