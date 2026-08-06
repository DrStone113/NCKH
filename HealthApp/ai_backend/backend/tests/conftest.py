import pytest
import db.db_status

@pytest.fixture(autouse=True)
def reset_db_status():
    """Autouse fixture to reset global database offline state before each test case."""
    db.db_status._db_offline_until = 0.0
