"""Immutable formula registry for approved ``nutrition-policy-v1.0.1``."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


_POLICY_PATH = Path(__file__).with_name("nutrition_policy_v1_0_1.json")
with _POLICY_PATH.open("r", encoding="utf-8") as policy_file:
    _loaded_policy: dict[str, Any] = json.load(policy_file)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


POLICY: Mapping[str, Any] = _deep_freeze(_loaded_policy)
POLICY_VERSION = str(POLICY["policy_version"])


@dataclass(frozen=True, slots=True)
class FormulaRegistryEntry:
    formula_id: str
    policy_version: str
    category: str
    source: str
    status: str
    units: str
    applicability: str
    limitations: str

    def to_dict(self) -> dict[str, str]:
        return {
            "formula_id": self.formula_id,
            "policy_version": self.policy_version,
            "category": self.category,
            "source": self.source,
            "status": self.status,
            "units": self.units,
            "applicability": self.applicability,
            "limitations": self.limitations,
        }


_entries = {
    item["formula_id"]: FormulaRegistryEntry(
        policy_version=POLICY_VERSION,
        **item,
    )
    for item in POLICY["registry"]
}
FORMULA_REGISTRY: Mapping[str, FormulaRegistryEntry] = MappingProxyType(_entries)


def formula_provenance(formula_ids: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    return [FORMULA_REGISTRY[formula_id].to_dict() for formula_id in formula_ids]


__all__ = [
    "FORMULA_REGISTRY",
    "FormulaRegistryEntry",
    "POLICY",
    "POLICY_VERSION",
    "formula_provenance",
]
