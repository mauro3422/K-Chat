from web.services.health_snapshot import checks_are_healthy


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
