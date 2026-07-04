# save_memory

Marks important user or system data for memory curation.

By default, `save_memory` writes a pending item to `memory/inbox/YYYY/MM/DD.jsonl`.
Use `scope="canonical"` only when the fact is durable and should go directly to
`MEMORY.md`, `memory.db`, and `source=memory` embeddings.

<!-- auto:params -->
| Parametro | Tipo | Requerido | Default | Descripcion |
|---|---|---|---|---|
| `key` | string | Si |  | Category or key of the information. |
| `value` | string | Si |  | Detail to save. Empty value deletes the key from canonical memory. |
| `scope` | string | No | inbox | `inbox` for curator review, `canonical` for direct durable memory. |
| `channel` | string | No |  | Optional source channel: web, telegram, cli, curator. |
| `message_ref` | string | No |  | Optional source message or turn reference. |
| `urgency` | string | No | normal | Review urgency: `normal` or `high`. |

---

Rules:

- Normal chat discoveries go to inbox.
- Use canonical only when Mauro explicitly asks for stable memory or a curator promotes it.
- Empty `value` remains a canonical delete operation for compatibility with `delete_memory`.
- Inbox items may be embedded as `source=memory_inbox`; canonical memories embed as `source=memory`.
