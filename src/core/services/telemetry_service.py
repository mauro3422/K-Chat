import json
import time
import logging
from pathlib import Path
from typing import Any

class TelemetryService:
    """Service to track system metrics and log them in a structured JSON format."""
    
    def __init__(self, log_file: str = "logs/telemetry.json"):
        # Ensure the logs directory exists relative to the current working directory
        self.log_file = Path(log_file)
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to a temporary directory if logs/ is not writable
            import tempfile
            self.log_file = Path(tempfile.gettempdir()) / "kchat_telemetry.json"

        # Configure a dedicated logger for telemetry
        self.logger = logging.getLogger("telemetry")
        self.logger.setLevel(logging.INFO)
        
        # Avoid duplicate handlers if initialized multiple times
        if not self.logger.handlers:
            try:
                handler = logging.FileHandler(self.log_file)
                handler.setFormatter(logging.Formatter('%(message)s'))
                self.logger.addHandler(handler)
            except Exception as e:
                # If file logging fails, fallback to stream logging
                stream_handler = logging.StreamHandler()
                stream_handler.setFormatter(logging.Formatter('TELEMETRY: %(message)s'))
                self.logger.addHandler(stream_handler)
                self.logger.error(f"Failed to initialize telemetry file handler: {e}")

    def log_event(self, event_type: str, data: dict[str, Any]):
        """Logs a generic event with a timestamp and type."""
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            **data
        }
        self.logger.info(json.dumps(event))

    def track_llm_usage(self, model: str, tokens: int, latency: float):
        """Specific method to track LLM metrics."""
        self.log_event("llm_usage", {
            "model": model,
            "tokens": tokens,
            "latency": latency
        })

    def track_tool_execution(self, tool_name: str, success: bool, duration: float):
        """Specific method to track tool execution metrics."""
        self.log_event("tool_execution", {
            "tool_name": tool_name,
            "success": success,
            "duration": duration
        })
