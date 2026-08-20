"""Stable error codes emitted by research experiment runs."""

from __future__ import annotations

import re


class ExperimentError(RuntimeError):
    """A controlled experiment failure with a machine-readable code."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
)


def safe_error_detail(exc: BaseException, *, limit: int = 500) -> str:
    """Return a bounded error description with common secret forms removed."""

    detail = f"{type(exc).__name__}: {exc}"
    for pattern in _SECRET_PATTERNS:
        detail = pattern.sub("[REDACTED]", detail)
    return detail[:limit]


__all__ = ["ExperimentError", "safe_error_detail"]
