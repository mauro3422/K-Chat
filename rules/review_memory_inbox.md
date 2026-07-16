# review_memory_inbox
**Review grouped save_memory inbox items. Lists repeated facts, promotes a group to canonical memory, or rejects noisy items.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `action` | string | No | list | Inbox review action. Values: list, inspect, promote, reject |
| `group_id` | string | No |  | Inbox group id or source inbox_id for promote/reject. |
| `include_recall_context` | boolean | No | false | Include layered recall context in inspect output. |
| `key` | string | No |  | Optional canonical key override when promoting. |
| `limit` | integer | No | 20 | Maximum groups to show. |
| `reason` | string | No |  | Reason for rejecting a group. |
| `root` | string | No |  | Optional project root. |
| `status` | string | No | pending | Status filter for list. |
| `value` | string | No |  | Optional canonical value override when promoting. |
