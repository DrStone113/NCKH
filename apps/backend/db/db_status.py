import time
import logging


def is_connectivity_failure(exc: BaseException) -> bool:
    """Return true only for a real database availability failure.

    Constraint violations and other application/data errors must remain local;
    treating them as an outage hides defects and causes unrelated sessions to
    skip their required persistence lifecycle.
    """
    text = str(exc).casefold()
    return any(marker in text for marker in (
        "connection refused", "connection reset", "connection is closed",
        "server closed the connection", "network is unreachable",
        "could not connect", "timeout", "timed out",
    ))

logger = logging.getLogger(__name__)

_db_offline_until: float = 0.0


def mark_db_offline(duration_s: float = 60.0) -> None:
    global _db_offline_until
    _db_offline_until = time.time() + duration_s


def is_db_offline() -> bool:
    return time.time() < _db_offline_until
