from src.memory.engine_state import configure_engine, get_engine, reset_engine


class _DummyEngine:
    def connect(self):
        return None

    def execute(self, conn, sql, params=()):
        return None

    def commit(self, conn):
        return None

    def rollback(self, conn):
        return None

    def close(self, conn):
        return None


def test_configure_engine_sets_explicit_instance():
    engine = _DummyEngine()
    configure_engine(engine)
    try:
        assert get_engine() is engine
    finally:
        reset_engine()


def test_reset_engine_clears_explicit_instance():
    engine = _DummyEngine()
    configure_engine(engine)
    reset_engine()
    assert get_engine() is None
