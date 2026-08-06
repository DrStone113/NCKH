import time
import logging

logger = logging.getLogger(__name__)

_db_offline_until: float = 0.0


def mark_db_offline(duration_s: float = 60.0) -> None:
    global _db_offline_until
    _db_offline_until = time.time() + duration_s


def is_db_offline() -> bool:
    return time.time() < _db_offline_until
