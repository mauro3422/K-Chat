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

from contextvars import ContextVar

from src.logbus.core import LogBus, LogEvent

_current_bus: ContextVar[LogBus | None] = ContextVar("kairos_logbus", default=None)


def configure_logbus(bus: LogBus | None) -> None:
    """Set the active LogBus instance for the current context."""
    _current_bus.set(bus)


def get_logbus() -> LogBus:
    """Get or create the LogBus for the current context."""
    bus = _current_bus.get()
    if bus is None:
        bus = LogBus()
        _current_bus.set(bus)
    return bus


def reset_logbus() -> None:
    """Reset the active LogBus instance for the current context."""
    configure_logbus(None)


def emit(event: LogEvent) -> None:
    """Convenience: emit an event to the global LogBus."""
    bus = get_logbus()
    bus.emit(event)


__all__ = ["LogBus", "LogEvent", "configure_logbus", "get_logbus", "reset_logbus", "emit"]
