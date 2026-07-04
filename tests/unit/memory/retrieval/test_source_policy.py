from src.memory.retrieval.source_policy import (
    approve_weight_policy_draft,
    build_weight_policy_draft,
    compare_policy_rankings,
    default_weights,
    draft_policy_path,
    load_weight_policy,
    policy_path,
    source_layer_policy_from_file,
    write_weight_policy_draft,
)


class FakeResult:
    def __init__(self, source, source_key, score, text=""):
        self.source = source
        self.source_key = source_key
        self.fusion_score = score
        self.text = text


def test_load_weight_policy_falls_back_to_builtin(tmp_path):
    policy = load_weight_policy(tmp_path)

    assert policy["version"] == "builtin"
    assert policy["weights"]["memory"] == 1.0
    assert policy["path"] == ""


def test_source_layer_policy_from_file_reads_approved_json(tmp_path):
    path = policy_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"version": "v1", "status": "approved", "weights": {"memory": 1.0, "memory_candidate": 0.81}}',
        encoding="utf-8",
    )

    policy = source_layer_policy_from_file(tmp_path)

    assert policy.weight_for("memory_candidate") == 0.81
    assert policy.weight_for("memory") == 1.0


def test_build_weight_policy_draft_only_changes_nonzero_deltas(tmp_path):
    draft = build_weight_policy_draft(
        [
            {
                "source": "remember",
                "layer": "memory_candidate",
                "current_weight": 0.78,
                "proposed_weight": 0.82,
                "delta": 0.04,
                "sample_size": 4,
                "rationale": "positive curator outcomes dominate",
            },
            {
                "source": "session_summary",
                "layer": "session_summary",
                "current_weight": 0.9,
                "proposed_weight": 0.9,
                "delta": 0.0,
            },
        ],
        root=tmp_path,
        timestamp="2026-07-04T10:00:00",
    )

    assert draft["status"] == "draft"
    assert draft["apply_policy"] == "manual_review_required"
    assert draft["weights"]["memory_candidate"] == 0.82
    assert draft["weights"]["session_summary"] == default_weights()["session_summary"]
    assert draft["changes"] == [
        {
            "layer": "memory_candidate",
            "source": "remember",
            "current_weight": 0.78,
            "proposed_weight": 0.82,
            "delta": 0.04,
            "sample_size": 4,
            "rationale": "positive curator outcomes dominate",
        }
    ]


def test_write_weight_policy_draft_writes_non_active_artifact(tmp_path):
    draft = write_weight_policy_draft(
        [
            {
                "source": "memory_inbox",
                "layer": "memory_inbox",
                "current_weight": 0.72,
                "proposed_weight": 0.68,
                "delta": -0.04,
            }
        ],
        root=tmp_path,
        timestamp="2026-07-04T10:00:00",
    )

    assert draft["path"] == str(draft_policy_path(tmp_path))
    assert draft_policy_path(tmp_path).exists()
    assert not policy_path(tmp_path).exists()


def test_approve_weight_policy_draft_promotes_to_approved_file(tmp_path):
    write_weight_policy_draft(
        [
            {
                "source": "remember",
                "layer": "memory_candidate",
                "current_weight": 0.78,
                "proposed_weight": 0.82,
                "delta": 0.04,
            }
        ],
        root=tmp_path,
        timestamp="2026-07-04T10:00:00",
    )

    approved = approve_weight_policy_draft(
        root=tmp_path,
        approved_by="mauro",
        reason="curator reviewed",
        timestamp="2026-07-04T10:05:00",
    )

    assert approved["status"] == "approved"
    assert approved["approved_by"] == "mauro"
    assert approved["approval_reason"] == "curator reviewed"
    assert approved["path"] == str(policy_path(tmp_path))
    assert load_weight_policy(tmp_path)["weights"]["memory_candidate"] == 0.82


def test_compare_policy_rankings_shows_rank_shift_from_approved_weights(tmp_path):
    path = policy_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        (
            '{"version": "v1", "status": "approved", '
            '"weights": {"memory": 1.0, "memory_candidate": 1.0, "memory_inbox": 0.72}}'
        ),
        encoding="utf-8",
    )

    audit = compare_policy_rankings(
        [
            FakeResult("memory", "user:canon", 0.7, "canon"),
            FakeResult("memory_candidate", "cand-1", 0.8, "candidate"),
        ],
        root=tmp_path,
    )

    assert audit["has_approved_policy"] is True
    assert audit["approved_policy_version"] == "v1"
    assert audit["rows"][0]["source"] == "memory_candidate"
    assert audit["rows"][0]["builtin_rank"] == 2
    assert audit["rows"][0]["approved_rank"] == 1
