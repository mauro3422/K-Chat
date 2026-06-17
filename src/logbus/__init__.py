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

# Singleton global — initialized lazily via init()
_logbus: LogBus | None = None


def get_logbus() -> LogBus:
    """Get the global LogBus singleton, creating it if needed."""
    global _logbus
    if _logbus is None:
        _logbus = LogBus()
    return _logbus


def emit(event: LogEvent) -> None:
    """Convenience: emit an event to the global LogBus."""
    bus = get_logbus()
    bus.emit(event)


__all__ = ["LogBus", "LogEvent", "get_logbus", "emit"]
