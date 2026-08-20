"""Validated immutable data models used only by research mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperimentProfile(BaseModel):
    """Explicit profile fixture; never populated from Firebase or live state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(min_length=1, max_length=200)
    age: int = Field(ge=18, le=120)
    sex: Literal["male", "female"]
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=300)
    activity_level: Literal[
        "sedentary", "light", "moderate", "active", "very_active"
    ]
    goal: Literal["lose_weight", "maintain", "gain_muscle"]
    target_weight_kg: float | None = Field(default=None, ge=30, le=300)
    dietary_restrictions: tuple[str, ...] = ()
    allergies: tuple[str, ...] = ()
    food_preferences: tuple[str, ...] = ()

    @field_validator("profile_id")
    @classmethod
    def _strip_profile_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("profile_id must not be blank")
        return value

    @field_validator(
        "dietary_restrictions", "allergies", "food_preferences", mode="before"
    )
    @classmethod
    def _normalize_string_collection(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            raise ValueError("must be an array of strings")
        cleaned = {str(item).strip() for item in value if str(item).strip()}
        return tuple(sorted(cleaned, key=str.casefold))

    def tdee_arguments(self) -> dict[str, object]:
        """Map the research vocabulary to the existing deterministic formula."""

        return {
            "user_id": self.profile_id,
            "age": self.age,
            "gender": self.sex,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "activity_level": self.activity_level,
            "health_goal": self.goal,
            "dietary_restrictions": list(self.dietary_restrictions),
        }


class ExperimentTestCase(BaseModel):
    """One query/profile pair executed independently under a condition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_case_id: str = Field(min_length=1, max_length=200)
    user_query: str = Field(min_length=1, max_length=20_000)
    profile: ExperimentProfile

    @field_validator("test_case_id", "user_query")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class FrozenRagChunk(BaseModel):
    """Serializable evidence returned from the frozen research corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    rank: int = Field(ge=1)
    title: str
    content: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: dict[str, Any]
    cosine_similarity: float = Field(ge=-1.0, le=1.0)
    keyword_score: float | None = Field(default=None, ge=0.0)
    fusion_score: float = Field(ge=0.0)


class RetrievalTrace(BaseModel):
    """Unambiguous retrieval telemetry embedded in each C/D run record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    expanded_query: str | None = None
    top_k: int = Field(ge=1)
    threshold: float = Field(ge=-1.0, le=1.0)
    retrieval_latency_ms: float = Field(ge=0.0)
    corpus_version: str
    corpus_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: tuple[FrozenRagChunk, ...]


@dataclass(frozen=True, slots=True)
class ResearchContext:
    """The exact initial LLM context and separately supplied tool schemas."""

    rendered_system_prompt: str
    messages: tuple[dict[str, Any], ...]
    tool_schemas: tuple[dict[str, Any], ...]
    rag_chunks: tuple[FrozenRagChunk, ...]


__all__ = [
    "ExperimentProfile",
    "ExperimentTestCase",
    "FrozenRagChunk",
    "RetrievalTrace",
    "ResearchContext",
]
