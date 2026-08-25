"""Conservative PII/auth redaction for natural shadow validation artifacts."""

from __future__ import annotations

import re


_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s.()-]?){8,15}(?!\d)")
_AUTH = re.compile(
    r"(?i)\b(?:bearer\s+[a-z0-9._~+/=-]+|sk-[a-z0-9_-]{8,}|"
    r"(?:password|mat\s*khau|api[_ -]?key|access[_ -]?token|auth(?:entication)?\s*value)"
    r"\s*[:=]\s*[^\s,;]+)"
)
_NAME = re.compile(
    r"(?i)\b(?:t[oô]i\s+t[eê]n\s+l[aà]|m[iy]\s+name\s+is)\s+"
    r"[^,.;!?\n]{1,80}"
)
_COMMON_NAME = re.compile(
    r"\b(?:Nguyễn|Trần|Lê|Phạm|Hoàng|Huỳnh|Phan|Vũ|Võ|Đặng|Bùi|Đỗ|Hồ|Ngô|Dương|Lý)"
    r"(?:\s+[A-ZĐÀ-Ỹ][a-zà-ỹđ]+){1,3}\b"
)
_TITLED_NAME = re.compile(
    r"(?i)\b(?:mr|mrs|ms|dr|anh|chị|chi|ông|ong|bà|ba)\.?\s+"
    r"[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){0,3}\b"
)
_ADDRESS = re.compile(
    r"(?i)\b(?:địa\s*chỉ|dia\s*chi|address|sống\s+tại|song\s+tai|live\s+at)"
    r"\s*[:=]?\s*[^.;!?\n]{3,120}"
)
_STREET_ADDRESS = re.compile(
    r"(?i)(?<!\d)\d{1,5}[/-]?[A-Za-z]?\s+"
    r"(?:đường\s+|duong\s+)?[A-ZÀ-Ỹ][\wÀ-ỹđĐ-]+"
    r"(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹđĐ-]+){1,4}"
)


def redact_query(text: str) -> tuple[str, tuple[str, ...]]:
    """Return redacted text and stable category labels, never matched values."""

    redacted = text
    labels: list[str] = []
    for label, pattern, replacement in (
        ("AUTH", _AUTH, "[AUTH_REDACTED]"),
        ("EMAIL", _EMAIL, "[EMAIL_REDACTED]"),
        ("PHONE", _PHONE, "[PHONE_REDACTED]"),
        ("ADDRESS", _ADDRESS, "[ADDRESS_REDACTED]"),
        ("ADDRESS", _STREET_ADDRESS, "[ADDRESS_REDACTED]"),
        ("NAME", _NAME, "[NAME_REDACTED]"),
        ("NAME", _COMMON_NAME, "[NAME_REDACTED]"),
        ("NAME", _TITLED_NAME, "[NAME_REDACTED]"),
    ):
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            labels.append(label)
    return redacted, tuple(labels)


__all__ = ["redact_query"]
