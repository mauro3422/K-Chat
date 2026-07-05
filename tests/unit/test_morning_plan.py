import sys
from datetime import date

from src.memory.curator.curation_events import append_curation_decision, write_curation_report
from src.memory.curator.memory_inbox import append_memory_inbox_item
from src.memory.curator.recall_review import write_candidates
from src.memory.synthesis.morning_plan import (
    build_morning_plan,
    compact_morning_plan,
    coalesce_inbox_items,
    curation_feedback_summary,
    git_health,
    laptop_health,
    laptop_remediation_commands,
    memory_pipeline_status,
    memory_layer_pipeline_command,
    morning_report_command,
    morning_plan_path,
    relation_decision_summaries,
    retrieval_weight_recommendations,
    render_morning_plan_json,
    render_morning_plan,
    write_morning_plan,
)


def test_morning_plan_path_uses_daily_partition(tmp_path):
    path = morning_plan_path("2026-07-02", root=tmp_path)

    assert path == tmp_path / "memory" / "2026" / "07" / "02" / "morning-plan.md"


def test_daily_operational_commands_include_full_layer_pipeline():
    prepare = memory_layer_pipeline_command(date(2026, 7, 2))
    report = morning_report_command("2026-07-02")

    assert prepare.startswith("python scripts\\generate_session_summaries.py --date 2026-07-02")
    assert "--embed --candidates --transversal --transversal-candidates" in prepare
    assert "--embed-transversal --embed-candidates --embed-inbox" in prepare
    assert "--daily-synthesis --curation-report --json" in prepare
    assert report.startswith("python scripts\\daily_memory_report.py --date 2026-07-02 --preview --preflight")
    assert "--laptop-status-command" in report
    assert "kairos_remote.py doctor --node laptop --json" in report
    assert "--laptop-status-timeout 60 --json --compact-json" in report


def test_coalesce_inbox_items_groups_duplicate_facts():
    groups = coalesce_inbox_items(
        [
            {
                "inbox_id": "a",
                "key": "user:lenguaje",
                "value": "Mauro usa Python para scripts de memoria.",
                "created_at": "2026-07-03T11:53:11",
                "_artifact": "memory/inbox/2026/07/03.jsonl",
            },
            {
                "inbox_id": "b",
                "key": " user:lenguaje ",
                "value": "Mauro usa Python para scripts de memoria.",
                "created_at": "2026-07-03T11:53:12",
                "_artifact": "memory/inbox/2026/07/03.jsonl",
            },
        ]
    )

    assert len(groups) == 1
    assert groups[0]["group_id"] == "a"
    assert groups[0]["reinforcement_count"] == 2
    assert groups[0]["inbox_ids"] == ["a", "b"]
    assert groups[0]["first_seen"] == "2026-07-03T11:53:11"
    assert groups[0]["last_seen"] == "2026-07-03T11:53:12"


def test_build_morning_plan_collects_inbox_candidates_reports_and_synthesis(tmp_path):
    append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere plan diario.", "urgency": "high"},
        root=tmp_path,
        timestamp="2026-07-02T08:00:00",
    )
    append_memory_inbox_item(
        {"key": "user:pref", "value": "Mauro quiere plan diario.", "urgency": "high"},
        root=tmp_path,
        timestamp="2026-07-02T08:01:00",
    )
    candidate_path = tmp_path / "memory" / "2026" / "07" / "02" / "candidates" / "recall_links.jsonl"
    write_candidates(
        candidate_path,
        [
            {
                "candidate_id": "cand-1",
                "status": "pending",
                "source": "remember",
                "query": "Kairos memoria",
                "relation_type": "LINKS_TO",
                "source_id": "candidate:cand-1",
                "target_id": "memory:semantic-neighbor",
                "target_needs_resolution": True,
                "link_score": 0.8,
                "proposed_relations": [
                    {
                        "source_id": "candidate:cand-1",
                        "target_id": "memory:semantic-neighbor",
                        "relation_type": "LINKS_TO",
                        "needs_resolution": True,
                    }
                ],
            },
            {
                "candidate_id": "cand-ready",
                "status": "ready_for_promotion",
                "source": "transversal_synthesis",
                "query": "memoria transversal",
                "relation_type": "LINKS_TO",
                "source_id": "candidate:cand-ready",
                "target_id": "memory:user:memory-policy",
                "target_needs_resolution": False,
                "link_score": 0.7,
            },
            {
                "candidate_id": "cand-semantic",
                "status": "pending",
                "source": "remember",
                "query": "Mauro quiere conectar recuerdos por embedding",
                "link_score": 0.42,
            }
        ],
    )
    write_curation_report(
        ["# Curation", "- tracer: 1 patterns found"],
        {"tracer_patterns": 1},
        root=tmp_path,
        timestamp="2026-07-02T07:00:00",
    )
    append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "promote",
            "group_id": "inbox-g1",
            "reinforcement_count": 2,
            "relation_hints": [
                {
                    "source_id": "inbox:i1",
                    "target_id": "memory:user:pref",
                    "relation_type": "PROMOTED_TO",
                }
            ],
        },
        root=tmp_path,
        timestamp="2026-07-02T08:30:00",
    )
    append_curation_decision(
        {
            "kind": "memory_relation",
            "action": "upsert_relation",
            "source_id": "memory:user:pref",
            "target_id": "entity:kairos",
            "relation_type": "SUPPORTS",
            "weight": 0.82,
            "evidence": "Mauro conecto esta preferencia con Kairos.",
            "curated_relation_id": "rel-1",
        },
        root=tmp_path,
        timestamp="2026-07-02T08:40:00",
    )
    synthesis_path = tmp_path / "memory" / "2026" / "07" / "02" / "daily.md"
    synthesis_path.parent.mkdir(parents=True, exist_ok=True)
    synthesis_path.write_text("# Daily Synthesis\n\n- Work happened\n", encoding="utf-8")

    plan = build_morning_plan(root=tmp_path, target_date=date(2026, 7, 2))

    assert len(plan["pending_inbox"]) == 2
    assert len(plan["inbox_groups"]) == 1
    assert plan["inbox_groups"][0]["reinforcement_count"] == 2
    assert len(plan["candidate_cards"]) == 2
    assert len(plan["ready_candidate_cards"]) == 1
    assert plan["ready_candidate_cards"][0]["candidate_id"] == "cand-ready"
    assert "curator_workbench action=explain" in plan["candidate_cards"][0]["review_command"]
    assert "curator_workbench action=map" in plan["candidate_cards"][0]["map_command"]
    assert plan["curation_report"]["metadata"] == {"tracer_patterns": 1}
    assert len(plan["curation_decisions"]) == 2
    assert any(item["source"] == "memory_inbox" for item in plan["curation_feedback"])
    assert any(item["source"] == "curated_relation" for item in plan["curation_feedback"])
    assert "weight_recommendations" in plan
    assert "weight_policy_draft" in plan
    assert plan["curation_decisions"][0]["group_id"] == "inbox-g1"
    manual_relation = next(item for item in plan["relation_decisions"] if item["action"] == "upsert_relation")
    assert manual_relation["source_id"] == "memory:user:pref"
    assert manual_relation["relation_type"] == "SUPPORTS"
    assert manual_relation["explain_command"] == "curator_workbench action=explain_relation relation_id=rel-1"
    assert plan["daily_synthesis"]["path"] == str(synthesis_path)
    assert "git" in plan["health"]
    assert plan["health"]["laptop"]["status"] == "not_configured"
    assert plan["pipeline_commands"]["prepare_layers"].startswith(
        "python scripts\\generate_session_summaries.py --date 2026-07-02"
    )
    assert "--embed-inbox" in plan["pipeline_commands"]["prepare_layers"]
    assert "--laptop-status-timeout 60 --json --compact-json" in plan["pipeline_commands"]["compact_report"]
    assert plan["pipeline_status"]["status"] == "attention"
    assert plan["pipeline_status"]["inbox_groups"] == 1
    assert plan["pipeline_status"]["pending_candidates"] == 2
    assert plan["pipeline_status"]["ready_candidates"] == 1
    assert "promote 1 ready candidate(s)" in plan["pipeline_status"]["next_steps"]
    inbox_action = next(action for action in plan["actions"] if action["kind"] == "inbox")
    assert inbox_action["reinforcement_count"] == 2
    assert "reforzado=2" in inbox_action["detail"]
    assert "include_recall_context=true" in inbox_action["recommended_command"]
    assert "review_memory_inbox action=promote" in inbox_action["promote_command"]
    assert "review_memory_inbox action=reject" in inbox_action["reject_command"]
    relation_action = next(action for action in plan["actions"] if action["kind"] == "relation_hints")
    assert relation_action["relation_hint_count"] == 1
    assert relation_action["preview_command"] == "curator_workbench action=preview_hints"
    assert relation_action["recommended_command"] == "curator_workbench action=preview_hints"
    assert relation_action["materialize_command"] == "curator_workbench action=materialize_hints"
    semantic_action = next(action for action in plan["actions"] if action["kind"] == "semantic_relation_hints")
    assert semantic_action["next_action"] == "recall_packet"
    assert "curator_workbench action=recall_packet" in semantic_action["recommended_command"]
    assert semantic_action["anchor_candidate_id"] == "cand-semantic"
    assert any(action["kind"] == "candidate_ready" for action in plan["actions"])
    pending_action = next(action for action in plan["actions"] if action["id"] == "cand-1")
    assert "action=map" in pending_action["detail"]
    assert "action=map" in pending_action["map_command"]
    ready_action = next(action for action in plan["actions"] if action["kind"] == "candidate_ready")
    assert "action=preview_relations" in ready_action["detail"]
    assert "action=preview_relations" in ready_action["recommended_command"]
    assert "action=promote_ready" in ready_action["followup_command"]
    assert "candidate_id=cand-ready" in ready_action["detail"]
    assert "action=explain" in ready_action["review_command"]
    assert "action=promote_ready" in ready_action["promotion_command"]


def test_render_morning_plan_contains_actionable_sections(tmp_path):
    plan = {
        "date": "2026-07-02",
        "pending_inbox": [{"inbox_id": "i1"}],
        "inbox_groups": [{"group_id": "i1"}],
        "candidate_cards": [{"candidate_id": "c1"}],
        "ready_candidate_cards": [{"candidate_id": "c2"}],
        "actions": [
            {
                "priority": 90,
                "kind": "inbox",
                "title": "Curar inbox: user:pref",
                "detail": "Detalle",
                "recommended_command": "review_memory_inbox action=inspect group_id=i1 include_recall_context=true",
                "followup_command": "review_memory_inbox action=promote group_id=i1",
                "fallback_command": "review_memory_inbox action=reject group_id=i1 reason=<reason>",
                "artifact": "memory/inbox/2026/07/02.jsonl",
            },
            {
                "priority": 82,
                "kind": "relation_hints",
                "title": "Materializar relaciones sugeridas por decisiones",
                "detail": (
                    "1 relation_hints; preview=curator_workbench action=preview_hints; "
                    "materialize=curator_workbench action=materialize_hints"
                ),
                "recommended_command": "curator_workbench action=preview_hints",
                "followup_command": "curator_workbench action=materialize_hints",
                "artifact": "memory/events/curation/2026/07/02.decisions.jsonl",
            },
            {
                "priority": 76,
                "kind": "semantic_relation_hints",
                "title": "Proponer relaciones desde vecinos semanticos",
                "detail": "1 candidato pendiente; anchor=c1",
                "recommended_command": "curator_workbench action=recall_packet query=\"Kairos memoria\" source=\"\" limit=8",
                "artifact": "memory/candidates/2026/07/02.recall_links.jsonl",
            }
        ],
        "curation_report": {"path": "", "preview": ["# Curation"], "metadata": {}},
        "curation_decisions": [
            {
                "kind": "memory_inbox",
                "action": "promote",
                "group_id": "inbox-g1",
                "reinforcement_count": 2,
            }
        ],
        "relation_decisions": [
            {
                "action": "upsert_relation",
                "kind": "memory_relation",
                "source_id": "memory:user:pref",
                "target_id": "entity:kairos",
                "relation_type": "SUPPORTS",
                "weight": 0.82,
                "evidence": "Mauro conecto preferencia con Kairos.",
                "explain_command": "curator_workbench action=explain_relation relation_id=rel-1",
            }
        ],
        "curation_feedback": [
            {
                "source": "memory_candidate",
                "total": 3,
                "positive_rate": 0.667,
                "negative_rate": 0.0,
                "blocked_rate": 0.333,
                "suggested_adjustment": "consider_raise",
                "actions": {"promote": 2, "needs_metadata": 1},
            }
        ],
        "weight_recommendations": [
            {
                "source": "memory_candidate",
                "layer": "memory_candidate",
                "current_weight": 0.78,
                "proposed_weight": 0.82,
                "delta": 0.04,
                "sample_size": 3,
                "apply_policy": "manual_review_required",
                "rationale": "positive curator outcomes dominate",
            }
        ],
        "weight_policy_draft": {
            "version": "20260704-100000",
            "status": "draft",
            "apply_policy": "manual_review_required",
            "path": "memory/policies/retrieval_weights.draft.json",
            "changes": [
                {
                    "layer": "memory_candidate",
                    "current_weight": 0.78,
                    "proposed_weight": 0.82,
                    "delta": 0.04,
                    "sample_size": 3,
                }
            ],
        },
        "daily_synthesis": {"path": "", "preview": ["# Daily Synthesis"]},
        "pipeline_status": {
            "status": "attention",
            "inbox_groups": 1,
            "pending_candidates": 1,
            "ready_candidates": 1,
            "issues": ["working tree dirty (2 changed paths)"],
            "next_steps": ["curate 1 inbox group(s)"],
        },
        "pipeline_commands": {
            "prepare_layers": "python scripts\\generate_session_summaries.py --date 2026-07-02 --embed --candidates --transversal --transversal-candidates --embed-transversal --embed-candidates --embed-inbox --daily-synthesis --curation-report --json",
            "compact_report": "python scripts\\daily_memory_report.py --date 2026-07-02 --preview --preflight --laptop-status-command \"python ops\\remote\\kairos_remote.py doctor --node laptop --json\" --laptop-status-timeout 60 --json --compact-json",
            "runbook": "curator_workbench action=runbook",
            "runbook_top": "curator_workbench action=runbook item_id=top",
        },
        "health": {
            "git": {
                "available": True,
                "branch": "main",
                "changed": 2,
                "untracked": 1,
                "ahead": 0,
                "behind": 0,
                "stashes": 0,
                "warnings": ["working tree has 2 changed paths"],
            },
            "preflight": {},
            "laptop": {
                "status": "degraded",
                "warnings": ["memory_audit: exit=2"],
                "failed_checks": [{"name": "memory_audit", "detail": "exit=2"}],
            },
        },
    }

    text = render_morning_plan(plan)

    assert "Morning Memory Plan - 2026-07-02" in text
    assert "Today's Work" in text
    assert "Guided runbook: `curator_workbench action=runbook`" in text
    assert "Start here: `curator_workbench action=runbook item_id=top`" in text
    assert "Runbook: `curator_workbench action=runbook item_id=i1`" in text
    assert "Git: branch `main`" in text
    assert "Pipeline Status" in text
    assert "Status: `attention`" in text
    assert "curate 1 inbox group(s)" in text
    assert "Operational Commands" in text
    assert "Prepare memory layers: `python scripts\\generate_session_summaries.py --date 2026-07-02" in text
    assert "Compact report: `python scripts\\daily_memory_report.py --date 2026-07-02 --preview --preflight --laptop-status-command" in text
    assert "Laptop Remediation" in text
    assert "Remote memory audit detail" in text
    assert "Remote memory repair plan" in text
    assert "Remote repair apply, manual only" in text
    assert "Materializar relaciones sugeridas" in text
    assert "curator_workbench action=preview_hints" in text
    assert "curator_workbench action=materialize_hints" in text
    assert "Proponer relaciones desde vecinos semanticos" in text
    assert "curator_workbench action=recall_packet" in text
    assert "Command: `review_memory_inbox action=inspect group_id=i1 include_recall_context=true`" in text
    assert "Follow-up: `review_memory_inbox action=promote group_id=i1`" in text
    assert "Fallback: `review_memory_inbox action=reject group_id=i1 reason=<reason>`" in text
    assert "Curar inbox" in text
    assert "Inbox groups: 1" in text
    assert "Curation Decisions" in text
    assert "Relation Decisions" in text
    assert "Curation Feedback" in text
    assert "memory_candidate" in text
    assert "consider_raise" in text
    assert "Retrieval Weight Recommendations" in text
    assert "curator_workbench action=audit_weight_policy_suite" in text
    assert "curator_workbench action=write_weight_policy_draft" in text
    assert "0.78 -> 0.82" in text
    assert "manual_review_required" in text
    assert "Retrieval Weight Policy Draft" in text
    assert "retrieval_weights.draft.json" in text
    assert "memory:user:pref" in text
    assert "SUPPORTS" in text
    assert "curator_workbench action=explain_relation relation_id=rel-1" in text
    assert "inbox-g1" in text
    assert "Ready candidates: 1" in text
    assert "Recent Synthesis" in text


def test_render_morning_plan_json_is_machine_readable(tmp_path):
    plan = build_morning_plan(root=tmp_path, target_date=date(2026, 7, 2))

    text = render_morning_plan_json(plan)

    assert '"date": "2026-07-02"' in text
    assert '"health"' in text
    assert '"pipeline_status"' in text


def test_compact_morning_plan_derives_priorities_from_actions():
    plan = {
        "date": "2026-07-02",
        "actions": [
            {
                "priority": 90,
                "kind": "inbox",
                "id": "i1",
                "title": "Curar inbox: user:pref",
                "next_action": "inspect_inbox",
                "recommended_command": "review_memory_inbox action=inspect group_id=i1",
            }
        ],
        "health": {
            "git": {"branch": "main", "changed": 0, "untracked": 0, "ahead": 0, "behind": 0, "stashes": 0},
            "preflight": {"ok": True, "issues": [], "snapshot": {}},
            "laptop": {"status": "ok", "available": True, "warnings": []},
        },
        "pipeline_status": {"status": "attention"},
        "pipeline_commands": {
            "prepare_layers": "python scripts\\generate_session_summaries.py --date 2026-07-02 --embed --candidates --transversal --transversal-candidates --embed-transversal --embed-candidates --embed-inbox --daily-synthesis --curation-report --json",
            "compact_report": "python scripts\\daily_memory_report.py --date 2026-07-02 --preview --preflight --laptop-status-command \"python ops\\remote\\kairos_remote.py doctor --node laptop --json\" --laptop-status-timeout 60 --json --compact-json",
        },
    }

    compact = compact_morning_plan(plan)

    assert compact["commands"]["prepare_layers"].startswith("python scripts\\generate_session_summaries.py")
    assert compact["priorities"][0]["title"].startswith("Curar cola de memoria")
    assert compact["priorities"][0]["command"] == "curator_workbench action=runbook item_id=i1"
    assert compact["summary"] == "status=attention; actions=1; preflight=ok; laptop=ok"
    assert compact["risk"].startswith("Curar cola de memoria")


def test_compact_morning_plan_prioritizes_degraded_laptop_when_no_actions():
    plan = {
        "date": "2026-07-02",
        "actions": [],
        "health": {
            "git": {"branch": "main", "changed": 0, "untracked": 0, "ahead": 0, "behind": 0, "stashes": 0},
            "preflight": {"ok": True, "issues": [], "snapshot": {}},
            "laptop": {
                "status": "degraded",
                "available": True,
                "warnings": ["memory_audit: exit=2"],
                "failed_checks": [{"name": "memory_audit", "detail": "exit=2"}],
            },
        },
        "pipeline_status": {"status": "attention"},
    }

    compact = compact_morning_plan(plan)

    assert compact["priorities"][0]["title"] == "Revisar health de laptop"
    assert compact["priorities"][0]["reason"] == "memory_audit"
    assert "scripts/memory_audit.py --json" in compact["priorities"][0]["command"]
    assert "scripts/memory_repair.py --json" in compact["priorities"][0]["followup_command"]
    assert "--apply --vectorize-missing --prune-stale" in compact["priorities"][0]["manual_apply_command"]
    assert compact["health"]["laptop"]["remediation"][0]["kind"] == "diagnose"
    assert compact["summary"] == "status=attention; actions=0; preflight=ok; laptop=degraded"
    assert compact["risk"] == "Revisar health de laptop: memory_audit"


def test_laptop_remediation_commands_keep_remote_apply_manual():
    commands = laptop_remediation_commands(
        {
            "status": "degraded",
            "failed_checks": [{"name": "memory_audit", "detail": "exit=2"}],
        }
    )

    by_kind = {item["kind"]: item["command"] for item in commands}

    assert "scripts/memory_audit.py --json" in by_kind["diagnose"]
    assert "scripts/memory_repair.py --json" in by_kind["preview"]
    assert "--apply --vectorize-missing --prune-stale" in by_kind["manual_apply"]


def test_compact_morning_plan_prioritizes_layer_preparation_when_artifacts_are_missing():
    plan = {
        "date": "2026-07-02",
        "actions": [],
        "health": {
            "git": {"branch": "main", "changed": 0, "untracked": 0, "ahead": 0, "behind": 0, "stashes": 0},
            "preflight": {"ok": True, "issues": [], "snapshot": {}},
            "laptop": {"status": "ok", "available": True, "warnings": []},
        },
        "pipeline_commands": {
            "prepare_layers": "python scripts\\generate_session_summaries.py --date 2026-07-02 --embed --candidates --transversal --transversal-candidates --embed-transversal --embed-candidates --embed-inbox --daily-synthesis --curation-report --json",
        },
        "pipeline_status": {
            "status": "attention",
            "issues": ["no curation report found", "no daily synthesis found"],
        },
    }

    compact = compact_morning_plan(plan)

    assert compact["priorities"][0]["title"] == "Preparar capas de memoria antes del plan"
    assert compact["priorities"][0]["command"].startswith("python scripts\\generate_session_summaries.py")


def test_relation_decision_summaries_extracts_hints_and_manual_relations():
    summaries = relation_decision_summaries(
        [
            {
                "kind": "memory_inbox",
                "action": "promote",
                "value": "Mauro usa Python.",
                "reinforcement_count": 2,
                "relation_hints": [
                    {
                        "source_id": "inbox:i1",
                        "target_id": "memory:user:lenguaje",
                        "relation_type": "PROMOTED_TO",
                    }
                ],
            },
            {
                "kind": "memory_relation",
                "action": "upsert_relation",
                "source_id": "memory:user:pref",
                "target_id": "entity:kairos",
                "relation_type": "SUPPORTS",
                "weight": 0.8,
                "evidence": "manual",
            },
        ]
    )

    assert [item["relation_type"] for item in summaries] == ["PROMOTED_TO", "SUPPORTS"]
    assert summaries[0]["weight"] == 2
    assert "source_id=inbox:i1" in summaries[0]["explain_command"]
    assert "candidate_id=" not in summaries[1]["explain_command"]
    assert summaries[1]["source_id"] == "memory:user:pref"


def test_curation_feedback_summary_groups_sources_and_suggests_adjustments():
    feedback = curation_feedback_summary(
        [
            {"kind": "memory_candidate", "source": "remember", "action": "promote", "relation_type": "REFINES"},
            {"kind": "memory_candidate", "source": "remember", "action": "promote_ready", "relation_type": "SUPPORTS"},
            {"kind": "memory_candidate", "source": "remember", "action": "complete_metadata", "missing_fields": []},
            {"kind": "memory_inbox", "action": "reject"},
            {"kind": "memory_inbox", "action": "needs_metadata", "missing_fields": ["target_id"]},
            {"kind": "memory_inbox", "action": "reject"},
        ]
    )

    remember = next(item for item in feedback if item["source"] == "remember")
    inbox = next(item for item in feedback if item["source"] == "memory_inbox")

    assert remember["total"] == 3
    assert remember["positive"] == 3
    assert remember["suggested_adjustment"] == "consider_raise"
    assert remember["relation_types"] == {"REFINES": 1, "SUPPORTS": 1}
    assert inbox["negative"] == 2
    assert inbox["blocked"] == 1
    assert inbox["suggested_adjustment"] == "consider_lower"


def test_retrieval_weight_recommendations_are_conservative_and_manual():
    recommendations = retrieval_weight_recommendations(
        [
            {
                "source": "remember",
                "total": 4,
                "suggested_adjustment": "consider_raise",
            },
            {
                "source": "memory_inbox",
                "total": 3,
                "suggested_adjustment": "consider_lower",
            },
            {
                "source": "session_summary",
                "total": 2,
                "suggested_adjustment": "hold",
            },
        ],
        current_weights={
            "memory_candidate": 0.78,
            "memory_inbox": 0.72,
            "session_summary": 0.9,
        },
    )

    by_layer = {item["layer"]: item for item in recommendations}

    assert by_layer["memory_candidate"]["proposed_weight"] == 0.82
    assert by_layer["memory_candidate"]["apply_policy"] == "manual_review_required"
    assert by_layer["memory_inbox"]["proposed_weight"] == 0.68
    assert by_layer["session_summary"]["proposed_weight"] == 0.9


def test_memory_pipeline_status_marks_blocked_when_preflight_fails():
    status = memory_pipeline_status(
        {
            "pending_inbox": [],
            "inbox_groups": [],
            "candidate_cards": [],
            "ready_candidate_cards": [],
            "curation_decisions": [],
            "curation_report": {"path": "memory/events/curation/2026/07/02.md"},
            "daily_synthesis": {"path": "memory/synthesis/2026/07/02.md"},
            "transversal_synthesis": {
                "path": "memory/transversal/2026/07/02.md",
                "metadata": {"session_count": 2},
            },
            "health": {
                "git": {"dirty": False, "behind": 0, "stashes": 0},
                "preflight": {"ok": False, "issues": ["missing embeddings"]},
                "laptop": {"status": "ok"},
            },
        }
    )

    assert status["status"] == "blocked"
    assert "memory preflight has issues" in status["issues"]


def test_memory_pipeline_status_flags_degraded_laptop_without_blocking():
    status = memory_pipeline_status(
        {
            "pending_inbox": [],
            "inbox_groups": [],
            "candidate_cards": [],
            "ready_candidate_cards": [],
            "curation_decisions": [],
            "curation_report": {"path": "memory/events/curation/2026/07/02.md"},
            "daily_synthesis": {"path": "memory/synthesis/2026/07/02.md"},
            "transversal_synthesis": {
                "path": "memory/transversal/2026/07/02.md",
                "metadata": {"session_count": 0},
            },
            "health": {
                "git": {"dirty": False, "behind": 0, "stashes": 0},
                "preflight": {"ok": True, "issues": []},
                "laptop": {"status": "degraded"},
            },
        }
    )

    assert status["status"] == "attention"
    assert "laptop health degraded" in status["issues"]


def test_memory_pipeline_status_allows_empty_transversal_when_no_sessions_expected():
    status = memory_pipeline_status(
        {
            "pending_inbox": [],
            "inbox_groups": [],
            "candidate_cards": [],
            "ready_candidate_cards": [],
            "curation_decisions": [],
            "curation_report": {
                "path": "memory/events/curation/2026/07/02.md",
                "metadata": {
                    "session_summaries": 0,
                    "session_summary_candidates": 0,
                    "session_summary_embeddings": 0,
                    "transversal_candidates": 0,
                },
            },
            "daily_synthesis": {"path": "memory/synthesis/2026/07/02.md"},
            "transversal_synthesis": {
                "path": "memory/transversal/2026/07/02.md",
                "metadata": {"session_count": 0},
            },
            "health": {
                "git": {"dirty": False, "behind": 0, "stashes": 0},
                "preflight": {},
                "laptop": {"status": "ok"},
            },
        }
    )

    assert "transversal synthesis has no sessions" not in status["issues"]
    assert status["status"] == "ok"


def test_memory_pipeline_status_flags_empty_transversal_when_sessions_expected():
    status = memory_pipeline_status(
        {
            "pending_inbox": [],
            "inbox_groups": [],
            "candidate_cards": [],
            "ready_candidate_cards": [],
            "curation_decisions": [],
            "curation_report": {
                "path": "memory/events/curation/2026/07/02.md",
                "metadata": {"session_summaries": 2},
            },
            "daily_synthesis": {"path": "memory/synthesis/2026/07/02.md"},
            "transversal_synthesis": {
                "path": "memory/transversal/2026/07/02.md",
                "metadata": {"session_count": 0},
            },
            "health": {
                "git": {"dirty": False, "behind": 0, "stashes": 0},
                "preflight": {},
                "laptop": {"status": "ok"},
            },
        }
    )

    assert "transversal synthesis has no sessions" in status["issues"]
    assert status["status"] == "attention"


def test_laptop_health_reads_configured_json(tmp_path):
    status_path = tmp_path / "laptop-status.json"
    status_path.write_text(
        '{"available": true, "status": "ok", "node": "laptop", "warnings": ["battery low"]}',
        encoding="utf-8",
    )

    health = laptop_health(root=tmp_path, status_json=status_path)

    assert health["available"] is True
    assert health["status"] == "ok"
    assert health["node"] == "laptop"
    assert health["warnings"] == ["battery low"]


def test_laptop_health_uses_json_from_failed_command(tmp_path):
    script = tmp_path / "laptop_status.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "print(json.dumps({",
                "    'ok': False,",
                "    'node': 'linux',",
                "    'checks': [",
                "        {'name': 'ssh', 'ok': True, 'detail': 'ok'},",
                "        {'name': 'memory_audit', 'ok': False, 'detail': 'exit=2', 'hint': 'stale vectors'},",
                "    ],",
                "}))",
                "sys.exit(1)",
            ]
        ),
        encoding="utf-8",
    )

    health = laptop_health(root=tmp_path, command=f'"{sys.executable}" "{script}"')

    assert health["available"] is True
    assert health["status"] == "degraded"
    assert health["command_exit_code"] == 1
    assert any("memory_audit: exit=2" in warning for warning in health["warnings"])


def test_laptop_health_compacts_large_doctor_stdout(tmp_path):
    script = tmp_path / "laptop_status.py"
    long_stdout = "stale-vector-row " * 120
    script.write_text(
        "\n".join(
            [
                "import json",
                "print(json.dumps({",
                "    'ok': False,",
                "    'checks': [",
                f"        {{'name': 'memory_audit', 'ok': False, 'detail': 'exit=2', 'stdout': {long_stdout!r}}},",
                "    ],",
                "}))",
            ]
        ),
        encoding="utf-8",
    )

    health = laptop_health(root=tmp_path, command=f'"{sys.executable}" "{script}"')

    stdout = health["checks"][0]["stdout"]
    assert len(stdout) < len(long_stdout)
    assert "truncated" in stdout
    assert health["warnings"] == ["memory_audit: exit=2"]


def test_write_morning_plan_writes_markdown(tmp_path):
    append_memory_inbox_item(
        {"key": "bug:test", "value": "Algo para revisar."},
        root=tmp_path,
        timestamp="2026-07-02T08:00:00",
    )

    path = write_morning_plan(root=tmp_path, target_date=date(2026, 7, 2))

    text = path.read_text(encoding="utf-8")
    assert path.exists()
    assert "Morning Memory Plan - 2026-07-02" in text
    assert "bug:test" in text


def test_git_health_handles_non_repo(tmp_path):
    health = git_health(root=tmp_path)

    assert health["available"] is False
    assert health["warnings"]
