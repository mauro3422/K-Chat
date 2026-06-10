import os
import pytest
from unittest.mock import MagicMock

os.environ.setdefault("TESTING", "true")

@pytest.fixture
def mock_conn():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor
