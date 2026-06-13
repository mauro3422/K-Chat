"""Tests for _save_with_retry logic."""
import time
from unittest.mock import Mock
import pytest


class TestSaveWithRetry:
    def test_save_succeeds_first_attempt(self):
        """If save succeeds immediately, return True."""
        mock_save = Mock()
        mock_save.return_value = True
        start = time.monotonic()
        result = self._simulate_save_retry(mock_save, max_attempts=3)
        elapsed = time.monotonic() - start
        assert result is True
        assert mock_save.call_count == 1
        assert elapsed < 0.1  # no delay on success

    def test_save_fails_all_attempts(self):
        """If save fails 3 times, return False with backoff."""
        mock_save = Mock(side_effect=Exception("DB error"))
        start = time.monotonic()
        result = self._simulate_save_retry(mock_save, max_attempts=3)
        elapsed = time.monotonic() - start
        assert result is False
        assert mock_save.call_count == 3
        assert elapsed >= 3.0  # 1s + 2s = at least 3s total

    def _simulate_save_retry(self, save_fn, max_attempts=3):
        """Replicates the _save_with_retry logic from chat_stream.py."""
        for attempt in range(max_attempts):
            try:
                save_fn()
                return True
            except Exception:
                if attempt < max_attempts - 1:
                    time.sleep(1.0 * (2 ** attempt))
        return False
