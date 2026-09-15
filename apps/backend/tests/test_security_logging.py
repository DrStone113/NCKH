from __future__ import annotations

import logging

from services.security_logging import (
    CredentialRedactingAccessFilter,
    redact_access_path,
)


def test_redacts_websocket_query_token_without_changing_other_parameters() -> None:
    target = "/chat/stream?session_id=session-1&token=header.payload.signature"

    assert redact_access_path(target) == (
        "/chat/stream?session_id=session-1&token=[REDACTED]"
    )


def test_uvicorn_access_record_never_formats_the_raw_token() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1234",
            "GET",
            "/chat/stream?token=secret-value&session_id=session-1",
            "1.1",
            101,
        ),
        exc_info=None,
    )

    assert CredentialRedactingAccessFilter().filter(record) is True
    rendered = record.getMessage()
    assert "secret-value" not in rendered
    assert "token=[REDACTED]" in rendered


def test_uvicorn_websocket_record_never_formats_the_raw_token() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "WebSocket %s" [accepted]',
        args=(
            "127.0.0.1:1234",
            "/chat/stream?session_id=session-1&token=secret-value",
        ),
        exc_info=None,
    )

    assert CredentialRedactingAccessFilter().filter(record) is True
    rendered = record.getMessage()
    assert "secret-value" not in rendered
    assert "token=[REDACTED]" in rendered
