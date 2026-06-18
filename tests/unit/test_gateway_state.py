from src import gateway


def test_reset_gateway_state_clears_runtime_flags():
    gateway._services["x"] = {"running": True}
    gateway._shutdown = True
    gateway._start_time = 123.0
    gateway.verbose = True

    gateway.reset_gateway_state()

    assert gateway._services == {}
    assert gateway._shutdown is False
    assert gateway._start_time == 0.0
    assert gateway.verbose is False
