"""Logging helpers for the agent stack."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_PII_KEYS = {"weight_kg", "height_cm", "health_goal", "message"}


def mask_pii(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``record`` with health-related PII masked."""
    def mask(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: ("***" if k in _PII_KEYS else mask(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [mask(item) for item in value]
        return value

    return mask(deepcopy(record))


__all__ = ["mask_pii"]