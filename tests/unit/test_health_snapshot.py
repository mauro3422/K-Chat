from types import SimpleNamespace

from web.services.health_snapshot import build_health_runtime, checks_are_healthy


def test_checks_are_healthy_accepts_testing_database_skip():
    checks = {
        "database": "skipped",
        "llm_provider": "configured",
        "node_role": "secondary",
        "cluster_name": "kairos",
    }

    assert checks_are_healthy(checks, testing=True) is True


def test_checks_are_healthy_rejects_database_error_when_not_testing():
    checks = {
        "database": "error",
        "llm_provider": "configured",
        "node_role": "secondary",
        "cluster_name": "kairos",
    }

    assert checks_are_healthy(checks, testing=False) is False


def test_build_health_runtime_discards_non_finite_or_boolean_timestamps():
    sync, memory, failover = build_health_runtime(
        cfg=SimpleNamespace(node_role="secondary"),
        coordinator_snapshot={
            "last_memory_revision": float("nan"),
            "last_memory_sync": float("inf"),
        },
        coordinator_role="",
        queue_size=0,
        queue_pending=[],
        lease_snapshot=None,
        failover_snapshot={
            "last_check_at": True,
            "last_primary_seen_at": float("-inf"),
            "last_promotion_at": 4,
        },
    )

    assert sync["last_memory_revision"] == 0.0
    assert sync["last_memory_sync"] == 0.0
    assert memory["freshness"] == {
        "last_revision": 0.0,
        "last_sync": 0.0,
        "is_fresh": True,
    }
    assert failover["last_check_at"] == 0.0
    assert failover["last_primary_seen_at"] == 0.0
    assert failover["last_promotion_at"] == 4.0
