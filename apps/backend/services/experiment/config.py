"""Immutable, authoritative configuration for controlled experiments."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LegacyExperimentCondition = Literal["A", "B", "C", "D"]
NutritionAblationArm = Literal["S0", "S1", "S2", "S3"]
ExperimentCondition = Literal["A", "B", "C", "D", "S0", "S1", "S2", "S3"]

LEGACY_PROTOCOL_ID = "legacy-profile-first-a-d"
NUTRITION_ABLATION_PROTOCOL_ID = "nutrition-ablation-s0-s3-v1"
NUTRITION_ABLATION_PROMPT_VERSION = "nutrition-ablation-v1"
NUTRITION_ABLATION_ARMS: tuple[NutritionAblationArm, ...] = (
    "S0",
    "S1",
    "S2",
    "S3",
)

_CONDITION_FLAGS: dict[str, tuple[bool, bool, bool]] = {
    # Historical profile-first protocol. These mappings and their serialized
    # hashes are frozen and must remain unchanged.
    "A": (False, False, False),
    "B": (True, False, False),
    "C": (True, True, False),
    "D": (True, True, True),
    # Incremental ablation requested by the core NCKH research protocol.
    # Tuple order is profile, RAG, deterministic nutrition tools.
    "S0": (False, False, False),
    "S1": (False, True, False),
    "S2": (False, True, True),
    "S3": (True, True, True),
}


class ExperimentConfig(BaseModel):
    """A frozen configuration whose condition exclusively defines treatment.

    Treatment flags are properties rather than constructor fields. This makes
    inconsistent combinations such as ``condition='A', use_profile=True``
    impossible to construct. A/B/C/D retain the historical profile-first
    protocol; S0/S1/S2/S3 implement the RAG -> tools -> personalization
    incremental ablation without rewriting historical runs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    condition: ExperimentCondition
    model: str = Field(default="rk/llms/qwen-3.7-plus", min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int = 20_260_815
    max_tokens: int = Field(default=1200, ge=1, le=32_768)
    max_agent_steps: int = Field(default=4, ge=1, le=10)
    prompt_version: str = Field(default="research-v1", min_length=1)
    frozen_time: datetime = Field(
        default=datetime(2026, 8, 15, 9, 0, 0, tzinfo=timezone.utc)
    )
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_threshold: float = Field(default=0.6, ge=-1.0, le=1.0)
    corpus_version: str = Field(default="offline-v1-636", min_length=1)
    corpus_hash: str = Field(
        default="b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081",
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("model", "prompt_version", "corpus_version")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("frozen_time")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("frozen_time must be timezone-aware")
        return value

    @property
    def profile_enabled(self) -> bool:
        return _CONDITION_FLAGS[self.condition][0]

    @property
    def rag_enabled(self) -> bool:
        return _CONDITION_FLAGS[self.condition][1]

    @property
    def nutrition_tools_enabled(self) -> bool:
        return _CONDITION_FLAGS[self.condition][2]

    @property
    def protocol_id(self) -> str:
        if self.condition in NUTRITION_ABLATION_ARMS:
            return NUTRITION_ABLATION_PROTOCOL_ID
        return LEGACY_PROTOCOL_ID

    @property
    def fallback_models(self) -> tuple[str, ...]:
        """Research mode never has a fallback model."""

        return ()

    def serialize(self) -> dict[str, object]:
        """Return a JSON-safe representation including derived treatment."""

        payload = self.model_dump(mode="json")
        payload.update(
            {
                "profile_enabled": self.profile_enabled,
                "rag_enabled": self.rag_enabled,
                "nutrition_tools_enabled": self.nutrition_tools_enabled,
                "fallback_models": [],
            }
        )
        return payload

    def config_hash(self) -> str:
        """SHA-256 of canonical serialized configuration."""

        canonical = json.dumps(
            self.serialize(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "ExperimentCondition",
    "ExperimentConfig",
    "LEGACY_PROTOCOL_ID",
    "LegacyExperimentCondition",
    "NUTRITION_ABLATION_ARMS",
    "NUTRITION_ABLATION_PROMPT_VERSION",
    "NUTRITION_ABLATION_PROTOCOL_ID",
    "NutritionAblationArm",
]
