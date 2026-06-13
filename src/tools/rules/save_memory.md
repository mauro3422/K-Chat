# save_memory
**Persists key user or system data to MEMORY.md so it can be recalled in future sessions.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `key` | string | Sí |  | The category or key of the information (e.g. 'Name', 'Preference', 'Technology', 'Project'). |
| `value` | string | Sí |  | The value or detail to save. If passed empty, this key is removed from memory. |

---

⚠️ MEMORY.md se reescribe COMPLETO ordenado alfabéticamente por key cada vez que llamás save_memory.
🔍 Los valores guardados con `user:` (ej: user:name, user:language) son perfil del usuario.
💡 Ejemplo: `execute_action(action_name="save_memory", arguments={"key": "user:name", "value": "Mauro"})`