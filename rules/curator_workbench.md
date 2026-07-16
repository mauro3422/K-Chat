# curator_workbench
**Workbench for nightly memory curation. Lists reviewable candidates, inspects missing metadata, shows graph context, and traces provenance.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `action` | string | No | list | Workbench action. Values: list, queue, runbook, inspect, trace, graph, explain, map, preview_hints, materialize_hints, upsert_relation, explain_relation, recall_packet, preview_weight_policy, write_weight_policy_draft, approve_weight_policy, audit_weight_policy, audit_weight_policy_suite |
| `candidate_id` | string | No |  | Candidate id for inspect/trace/graph/map or optional relation provenance. |
| `depth` | integer | No | 1 | Graph depth, max 5. |
| `entity_id` | string | No |  | Entity id for graph action. |
| `evidence` | string | No |  | Evidence text for upsert_relation. |
| `item_id` | string | No |  | Queue item id for focused runbook output. |
| `known_entities` | array | No | [] | Optional known entities used to enrich recall graph context. |
| `limit` | integer | No | 20 | Maximum rows to return. |
| `memory_key` | string | No |  | Canonical memory key for graph action; expands to memory:<key>. |
| `path` | string | No |  | Optional candidate JSONL path for inspect/trace. |
| `query` | string | No |  | Recall/query text, or a |/newline-separated audit suite override. |
| `reason` | string | No |  | Curator reason for upsert_relation. |
| `relation_id` | string | No |  | Curated relation id for explain_relation. |
| `relation_type` | string | No |  | Relation type for upsert_relation or explain_relation. |
| `root` | string | No |  | Optional project/artifact root. Defaults to the Kairos project root. |
| `source` | string | No |  | Optional memory source filter for recall_packet. Values: , memory, session, session_summary, transversal_synthesis, memory_candidate, memory_inbox |
| `source_id` | string | No |  | Source id for upsert_relation, graph node lookup, or explain_relation. |
| `status` | string | No | pending | Status filter for list. Use empty string for all. |
| `target_id` | string | No |  | Target id for upsert_relation or graph node lookup. |
| `weight` | number | No | 1.0 | Relation weight for upsert_relation. |
