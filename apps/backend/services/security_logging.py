"""Redact credentials that legacy clients may place in access-log URLs."""

from __future__ import annotations

import logging
import re


_TOKEN_QUERY_RE = re.compile(r"([?&]token=)[^&\s]+", re.IGNORECASE)


def redact_access_path(value: str) -> str:
    return _TOKEN_QUERY_RE.sub(r"\1[REDACTED]", value)


class CredentialRedactingAccessFilter(logging.Filter):
    """Sanitize request-target arguments before Uvicorn formats them."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(
                redact_access_path(item) if isinstance(item, str) else item
                for item in args
            )
        return True


def install_access_log_redaction() -> None:
    # HTTP access records use uvicorn.access; WebSocket handshake records use
    # uvicorn.error in current Uvicorn releases.
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        if any(
            isinstance(item, CredentialRedactingAccessFilter)
            for item in logger.filters
        ):
            continue
        logger.addFilter(CredentialRedactingAccessFilter())


__all__ = [
    "CredentialRedactingAccessFilter",
    "install_access_log_redaction",
    "redact_access_path",
]
