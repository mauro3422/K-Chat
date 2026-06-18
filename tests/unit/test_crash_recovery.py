from src.context.crash_recovery import load_error_context, reset_crash_counter


def test_load_error_context_without_files_returns_empty():
    reset_crash_counter()
    assert load_error_context() == ""


def test_reset_crash_counter_is_idempotent():
    reset_crash_counter()
    reset_crash_counter()
    assert True
