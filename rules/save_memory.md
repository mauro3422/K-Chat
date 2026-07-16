# save_memory
**Mark important user or system data for memory curation. By default writes to the daily memory inbox; use scope='canonical' only for durable memories that should go directly to MEMORY.md.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `channel` | string | No |  | Optional source channel: web, telegram, cli, curator. |
| `key` | string | Sí |  | The category or key of the information (e.g. 'Name', 'Preference', 'Technology', 'Project'). |
| `message_ref` | string | No |  | Optional message or turn reference for curator source tracing. |
| `scope` | string | No | inbox | inbox marks an item for curator review; canonical writes directly to MEMORY.md. Values: inbox, canonical |
| `urgency` | string | No | normal | Review urgency for the daily curator. Values: normal, high |
| `value` | string | Sí |  | The value or detail to save. If passed empty, this key is removed from memory. |

---

⚠️ MEMORY.md se reescribe COMPLETO ordenado alfabéticamente por key cada vez que llamás save_memory.
🔍 Los valores guardados con `user:` (ej: user:name, user:language) son perfil del usuario.
💡 Ejemplo: `execute_action(action_name="save_memory", arguments={"key": "user:name", "value": "Mauro"})`
