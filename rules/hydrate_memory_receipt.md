# hydrate_memory_receipt
**Expand a compact memory receipt that appeared in the system context. Use its receipt ID to load the original memory, synthesis, or session exchange plus nearby conversational context. A query may be used to find matching receipt IDs from the current chat.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `context_window` | integer | No | 1 | Nearby session exchanges on each side (default 1, max 4). |
| `query` | string | No |  | Search recent receipts when the exact ID is unknown. |
| `receipt_id` | string | No |  | Receipt ID such as mr_0123456789abcdef. |
