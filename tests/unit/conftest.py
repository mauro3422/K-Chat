import os
import pytest
from unittest.mock import MagicMock, AsyncMock

os.environ.setdefault("TESTING", "true")

@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    cursor = AsyncMock()
    conn.execute.return_value = cursor
    conn.cursor.return_value = cursor # For backward compatibility if needed
    return conn, cursor
