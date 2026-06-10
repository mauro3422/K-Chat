from web.services.stream_error_classifier import classify_error, ERROR_MESSAGES


def test_rate_limit():
    etype, msg = classify_error("Rate limit reached for this API key")
    assert etype == "rate_limit"
    assert msg == ERROR_MESSAGES["rate_limit"]


def test_rate_limit_case_insensitive():
    etype, _ = classify_error("RATE LIMIT exceeded")
    assert etype == "rate_limit"


def test_timeout():
    etype, msg = classify_error("Request timeout after 30s")
    assert etype == "timeout"
    assert msg == ERROR_MESSAGES["timeout"]


def test_connection():
    etype, msg = classify_error("Connection refused by server")
    assert etype == "network"
    assert msg == ERROR_MESSAGES["network"]


def test_network_keyword():
    etype, msg = classify_error("Network error occurred")
    assert etype == "network"
    assert msg == ERROR_MESSAGES["network"]


def test_model_error():
    etype, msg = classify_error("Model returned an invalid response")
    assert etype == "model"
    assert msg == ERROR_MESSAGES["model"]


def test_api_error():
    etype, msg = classify_error("API key is invalid")
    assert etype == "model"
    assert msg == ERROR_MESSAGES["model"]


def test_unknown_error():
    etype, msg = classify_error("Something completely unexpected happened")
    assert etype == "unknown"
    assert msg == ERROR_MESSAGES["unknown"]


def test_empty_message():
    etype, _ = classify_error("")
    assert etype == "unknown"


def test_priority_rate_limit_over_connection():
    etype, _ = classify_error("rate limit and connection error")
    assert etype == "rate_limit"


def test_priority_timeout_over_model():
    etype, _ = classify_error("timeout in model API call")
    assert etype == "timeout"
