"""LogBus — unified async logging bus for K-Chat.

Usage:
    from src.logbus import logbus, LogEvent
    
    logbus.emit(LogEvent(
        level="INFO",
        module="chat",
        msg="chat_turn",
        session_id="abc-123",
        duration_ms=1500,
    ))
"""

from src.logbus.core import LogBus, LogEvent

_logbus: LogBus | None = None


def configure_logbus(bus: LogBus | None) -> None:
    """Set the active LogBus instance explicitly.

    Passing None resets the module to lazy initialization behavior.
    """
    global _logbus
    _logbus = bus


def get_logbus() -> LogBus:
    """Get the global LogBus singleton, creating it if needed."""
    global _logbus
    if _logbus is None:
        _logbus = LogBus()
    return _logbus


def reset_logbus() -> None:
    """Reset the active LogBus instance."""
    configure_logbus(None)


def emit(event: LogEvent) -> None:
    """Convenience: emit an event to the global LogBus."""
    bus = get_logbus()
    bus.emit(event)


__all__ = ["LogBus", "LogEvent", "configure_logbus", "get_logbus", "reset_logbus", "emit"]
