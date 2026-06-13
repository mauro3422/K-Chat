from unittest.mock import patch, MagicMock, Mock

import pytest

from src.llm.retry import execute_with_retry, is_rate_limit_error


@patch("src.llm.retry.time.sleep")
def test_execute_with_retry_success_on_first_try(mock_sleep):
    mock_fn = MagicMock(return_value="success")

    result = execute_with_retry(mock_fn, "test-model")

    assert result == "success"
    mock_fn.assert_called_once()
    mock_sleep.assert_not_called()


@patch("src.llm.retry.time.sleep")
def test_execute_with_retry_retries_on_rate_limit(mock_sleep):
    class RateLimitError(Exception):
        status_code = 429

    mock_fn = MagicMock(side_effect=[RateLimitError("Rate limit"), "success"])

    result = execute_with_retry(mock_fn, "test-model")

    assert result == "success"
    assert mock_fn.call_count == 2
    mock_sleep.assert_called()


@patch("src.llm.retry.time.sleep")
def test_execute_with_retry_uses_exponential_backoff(mock_sleep):
    class RateLimitError(Exception):
        status_code = 429

    mock_fn = MagicMock(side_effect=[RateLimitError("Rate limit"), "success"])

    execute_with_retry(mock_fn, "test-model")

    mock_sleep.assert_called_once()
    call_args = mock_sleep.call_args[0][0]
    assert call_args == 5.0


@patch("src.llm.retry.time.sleep")
def test_execute_with_retry_raises_after_max_retries(mock_sleep):
    class RateLimitError(Exception):
        status_code = 429

    mock_fn = MagicMock(side_effect=RateLimitError("Rate limit"))

    with pytest.raises(RateLimitError):
        execute_with_retry(mock_fn, "test-model")

    assert mock_fn.call_count == 3


def test_is_rate_limit_error_detects_rate_limit_error():
    from openai import RateLimitError
    mock_response = Mock()
    error = RateLimitError(message="Rate limit", response=mock_response, body=None)
    assert is_rate_limit_error(error) is True


def test_is_rate_limit_error_detects_status_code_429():
    class ErrorWithStatusCode(Exception):
        status_code = 429

    error = ErrorWithStatusCode("Too many requests")
    assert is_rate_limit_error(error) is True


def test_is_rate_limit_error_detects_text_patterns():
    error1 = Exception("rate limit")
    assert is_rate_limit_error(error1) is True

    error2 = Exception("RateLimit")
    assert is_rate_limit_error(error2) is True

    error3 = Exception("HTTP 429")
    assert is_rate_limit_error(error3) is True
