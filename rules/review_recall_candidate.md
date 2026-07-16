# review_recall_candidate
**Review recall link candidates materialized by the curator tracer. Can list, reject, apply a suggested target, mark missing metadata, complete metadata, or promote a reviewed candidate into the entity relation graph.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `action` | string | No | list | Review action to perform. Values: list, suggest_metadata, apply_target, complete_metadata, preview_relations, reject, needs_metadata, link_neighbor, promote, promote_ready |
| `candidate_id` | string | No |  | Candidate id for reject/needs_metadata/promote. |
| `limit` | integer | No | 20 | Maximum list results. |
| `missing_fields` | array | No | [] | Missing metadata fields. |
| `neighbor_candidate_id` | string | No |  | Neighbor candidate id for link_neighbor. |
| `path` | string | Sí |  | Path to a memory/candidates/*.recall_links.jsonl file. |
| `reason` | string | No |  | Review reason for reject or needs_metadata. |
| `relation_type` | string | No |  | Relation type for metadata completion, promotion, or link_neighbor. |
| `source_id` | string | No |  | Graph source entity/artifact id for metadata completion or promotion. |
| `target_id` | string | No |  | Graph target entity/artifact id for apply_target, metadata completion, or promotion. |
| `target_reason` | string | No |  | Reason attached to the selected target suggestion. |
| `target_score` | number | No |  | Score of the selected target suggestion. |
| `target_source` | string | No |  | Source of the selected target suggestion. |
| `weight` | number | No |  | Optional relation weight. |
