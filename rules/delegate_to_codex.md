# delegate_to_codex
**Create a work task for Codex on the primary PC. Use this when Mauro is on a secondary node and wants Codex to make a code/docs/config change, investigate a bug, or run an operational task.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `priority` | string | No | normal |  Values: low, normal, high, urgent |
| `prompt` | string | Sí |  | Concrete instructions, context, expected outcome, and anything Codex must report back. |
| `session_id` | string | No |  | Optional Kairos session id that originated the task. |
| `title` | string | Sí |  | Short task title for Codex. |
