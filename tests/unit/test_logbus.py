from src.logbus import LogBus, configure_logbus, get_logbus, reset_logbus


def test_configure_logbus_returns_explicit_bus():
    bus = LogBus()
    configure_logbus(bus)
    try:
        assert get_logbus() is bus
    finally:
        reset_logbus()


def test_reset_logbus_restores_lazy_instance():
    bus = LogBus()
    configure_logbus(bus)
    reset_logbus()
    new_bus = get_logbus()
    assert new_bus is not bus
