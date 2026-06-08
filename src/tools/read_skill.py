import os

# Definición de la tool para el modelo LLM
DEFINITION = {
    "type": "function",
    "function": {
        "name": "read_skill",
        "description": "Consulta las instrucciones detalladas de una habilidad (como 'html-widgets') cuando necesitas realizar una tarea especializada o programar interfaces visuales.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre de la habilidad a consultar (ej: 'html-widgets')."
                }
            },
            "required": ["name"]
        }
    }
}


def run(name: str, _session_id: str = None) -> str:
    """Lee y retorna el contenido de una habilidad desde la carpeta skills/."""
    # Sanitizar el nombre para evitar directory traversal
    safe_name = "".join(c for c in name if c.isalnum() or c in ("-", "_")).lower()
    if not safe_name:
        return "[ERROR] Nombre de habilidad inválido."

    # Obtener el path absoluto de la carpeta skills/
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    skills_dir = os.path.join(base_dir, "skills")
    file_path = os.path.join(skills_dir, f"{safe_name}.md")

    if not os.path.exists(file_path):
        # Listar las habilidades disponibles para guiar al modelo
        try:
            files = os.listdir(skills_dir)
            available = [os.path.splitext(f)[0] for f in files if f.endswith(".md") and f != "INDEX.md"]
        except Exception:
            available = ["html-widgets"]
        
        return f"[ERROR] Habilidad '{safe_name}' no encontrada. Habilidades disponibles: {', '.join(available)}"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[ERROR] No se pudo leer la habilidad '{safe_name}': {e}"
