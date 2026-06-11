ERROR_MESSAGES = {
    "rate_limit": "Rate limit reached. Wait a moment before retrying.",
    "timeout": "The model took too long to respond.",
    "network": "Connection error with the model.",
    "tool_error": "A tool or function call failed. Please try again.",
    "model": "The model encountered an error. Please try again.",
    "unknown": "An unexpected error occurred. Please try again.",
}


def classify_error(error_msg: str) -> tuple[str, str]:
    """Classifies an error message into a type and a user-friendly message."""
    msg_l = error_msg.lower()
    if "rate limit" in msg_l:
        return "rate_limit", ERROR_MESSAGES["rate_limit"]
    elif "timeout" in msg_l:
        return "timeout", ERROR_MESSAGES["timeout"]
    elif "connection" in msg_l or "network" in msg_l:
        return "network", ERROR_MESSAGES["network"]
    elif "tool" in msg_l or "function" in msg_l:
        return "tool_error", ERROR_MESSAGES["tool_error"]
    elif "model" in msg_l or "api" in msg_l:
        return "model", ERROR_MESSAGES["model"]
    return "unknown", ERROR_MESSAGES["unknown"]
