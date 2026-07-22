# manage_memory
**Maintenance operations for the memory system. Use 'reindex' to regenerate embeddings for MEMORY.md entries. Use 'reindex_sessions' to vectorize session exchanges. Use 'reindex_session <id>' for a single session. Use 'clusters' to see topic clusters. Use 'topics' to see the topic map. Use 'stats' to see memory system status. Use 'compare' to compare MEMORY.md vs memory.db. Use 'repair' to fix inconsistencies. Use 'sync' to sync memory.db from MEMORY.md. Use 'archive' to archive entries (prefix key with _archived:). Use 'find' to search in MEMORY.md. Use 'quality_stats' to audit graph/session hygiene. Use 'prune_entities' to remove generated low-signal leaves. Use 'cleanup_empty_sessions' to remove unused sessions. Use 'backfill_tool_calls' to recover historical tool metadata. Use 'prune_indirect_cooccurrence' to clean PMI noise around a semantic entity. Use 'rebuild_topic_relations' to regenerate cluster relations. Use 'export' to export as JSON.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `confirm` | boolean | No | false | If True, confirm destructive operations (default: False). |
| `dry_run` | boolean | No | false | If True, only count/show (default: False). |
| `entity_id` | string | No |  | Entity ID or exact name for graph cleanup operations. |
| `find_text` | string | No |  | Text to search for (used with 'find'). |
| `fmt` | string | No | text | Output format (default: text). Values: text, json |
| `key_pattern` | string | No |  | Filter by key pattern (e.g. 'user:*', 'bug:*'). Supports * wildcard. |
| `operation` | string | Sí |  | Operation to perform. Values: reindex, reindex_sessions, reindex_session, clusters, topics, stats, compare, repair, sync, archive, find, export, quality_stats, prune_entities, cleanup_empty_sessions, rebuild_topic_relations, backfill_tool_calls, prune_indirect_cooccurrence |
| `session_id` | string | No |  | Session ID for reindex_session (optional). |
