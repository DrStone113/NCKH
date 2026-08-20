"""Versioned benchmark schemas and cryptographic integrity helpers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.experiment.errors import ExperimentError
from services.experiment.models import ExperimentProfile

BENCHMARK_VERSION = "nutrition-benchmark-v1.0.0"
BENCHMARK_SCHEMA_VERSION = "1.0"
RUBRIC_VERSION = "human-rubric-v1.0.0"
COMPATIBLE_CORPUS_VERSION = "offline-v1-636"


class BenchmarkCategory(str, Enum):
    GENERAL_NUTRITION = "general_nutrition"
    ENERGY_CALCULATION = "energy_calculation"
    WEIGHT_MANAGEMENT = "weight_management"
    PERSONALIZED_RECOMMENDATION = "personalized_recommendation"
    VIETNAMESE_FOOD_KNOWLEDGE = "vietnamese_food_knowledge"
    MEAL_RECOMMENDATION = "meal_recommendation"
    DIETARY_CONSTRAINTS = "dietary_constraints"
    ALLERGY_CONSTRAINTS = "allergy_constraints"
    RAG_KNOWLEDGE_QUESTIONS = "rag_knowledge_questions"
    SAFETY_BOUNDARY_CASES = "safety_boundary_cases"


class BenchmarkSplit(str, Enum):
    DEVELOPMENT = "development"
    PILOT = "pilot"
    FINAL = "final"


class Answerability(str, Enum):
    ANSWERABLE_FROM_CORPUS = "answerable_from_corpus"
    NOT_ANSWERABLE_FROM_CORPUS = "not_answerable_from_corpus"
    CALCULATION_BASED = "calculation_based"
    CONSTRAINT_BASED = "constraint_based"


class RequiredFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    acceptable_terms: tuple[str, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = ()


class RequiredConstraint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    constraint_id: str = Field(min_length=1)
    constraint_type: Literal[
        "allergen_exclusion",
        "dietary_restriction",
        "energy_range",
        "goal_alignment",
        "safety_boundary",
        "preference",
    ]
    description: str = Field(min_length=1)
    prohibited_terms: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()


class ReferenceSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    source_type: Literal[
        "frozen_corpus_record", "guideline", "formula", "protocol"
    ]
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    url: str | None = None
    corpus_version: str | None = None
    dataset_file: str | None = None
    source_record_id: str | None = None
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _require_corpus_coordinates(self) -> "ReferenceSource":
        if self.source_type == "frozen_corpus_record":
            required = (
                self.corpus_version,
                self.dataset_file,
                self.source_record_id,
                self.content_hash,
            )
            if any(value is None for value in required):
                raise ValueError("corpus references require full immutable coordinates")
        return self


class ObjectiveExpectedValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value_id: str = Field(min_length=1)
    metric: Literal[
        "numerical_absolute_error",
        "numerical_relative_error",
        "calorie_target_error",
    ]
    expected: float
    unit: str = Field(min_length=1)
    absolute_tolerance: float = Field(default=0.0, ge=0.0)
    relative_tolerance: float = Field(default=0.0, ge=0.0)
    accepted_labels: tuple[str, ...] = Field(min_length=1)


class ScoringMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    answerability: Answerability
    research_questions: tuple[Literal["RQ1", "RQ2"], ...]
    objective_metrics: tuple[str, ...]
    human_rubrics: tuple[
        Literal[
            "factual_correctness",
            "personalization",
            "relevance",
            "completeness",
            "groundedness",
            "safety",
        ],
        ...,
    ]
    citation_required: bool = False
    notes: str = ""


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{4,79}$")
    category: BenchmarkCategory
    split: BenchmarkSplit
    user_query: str = Field(min_length=1, max_length=20_000)
    profile: ExperimentProfile
    required_facts: tuple[RequiredFact, ...]
    required_constraints: tuple[RequiredConstraint, ...]
    reference_sources: tuple[ReferenceSource, ...]
    objective_expected_values: tuple[ObjectiveExpectedValue, ...]
    safety_flags: tuple[str, ...]
    scoring_metadata: ScoringMetadata

    @model_validator(mode="after")
    def _validate_reference_links(self) -> "BenchmarkCase":
        source_ids = {source.source_id for source in self.reference_sources}
        if len(source_ids) != len(self.reference_sources):
            raise ValueError("reference source IDs must be unique within a case")
        for fact in self.required_facts:
            if not set(fact.source_ids).issubset(source_ids):
                raise ValueError(f"unknown source in required fact {fact.fact_id}")
        return self

    def case_hash(self) -> str:
        return sha256_canonical(self.model_dump(mode="json"))


class BenchmarkFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_version: str
    schema_version: str
    cases: tuple[BenchmarkCase, ...]

    @model_validator(mode="after")
    def _validate_cases(self) -> "BenchmarkFile":
        if self.benchmark_version != BENCHMARK_VERSION:
            raise ValueError("unsupported benchmark version")
        if self.schema_version != BENCHMARK_SCHEMA_VERSION:
            raise ValueError("unsupported benchmark schema version")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case IDs must be unique")
        return self


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_version: str
    schema_version: str
    case_count: int = Field(ge=1)
    category_counts: dict[str, int]
    split_counts: dict[str, int]
    benchmark_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    creation_commit: str | None
    creation_worktree_clean: bool | None
    rubric_version: str
    reference_source_versions: dict[str, str]
    corpus_version: str
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":") if indent is None else None,
            indent=indent,
        )
        + ("\n" if indent is not None else "")
    ).encode("utf-8")


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_benchmark(path: Path) -> BenchmarkFile:
    try:
        return BenchmarkFile.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ExperimentError("EXPERIMENT_BENCHMARK_INVALID", str(exc)[:500]) from exc


def load_and_verify_benchmark(
    benchmark_path: Path, manifest_path: Path
) -> tuple[BenchmarkFile, BenchmarkManifest]:
    benchmark = load_benchmark(benchmark_path)
    try:
        manifest = BenchmarkManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ExperimentError("EXPERIMENT_BENCHMARK_MANIFEST_INVALID", str(exc)[:500]) from exc

    payload = manifest.model_dump(mode="json")
    stored_manifest_hash = payload.pop("manifest_hash")
    if sha256_canonical(payload) != stored_manifest_hash:
        raise ExperimentError("EXPERIMENT_BENCHMARK_MANIFEST_HASH_MISMATCH")
    if sha256_file(benchmark_path) != manifest.benchmark_file_sha256:
        raise ExperimentError("EXPERIMENT_BENCHMARK_FILE_HASH_MISMATCH")
    if benchmark.benchmark_version != manifest.benchmark_version:
        raise ExperimentError("EXPERIMENT_BENCHMARK_VERSION_MISMATCH")
    if benchmark.schema_version != manifest.schema_version:
        raise ExperimentError("EXPERIMENT_BENCHMARK_SCHEMA_MISMATCH")
    if len(benchmark.cases) != manifest.case_count:
        raise ExperimentError("EXPERIMENT_BENCHMARK_COUNT_MISMATCH")

    categories = Counter(case.category.value for case in benchmark.cases)
    splits = Counter(case.split.value for case in benchmark.cases)
    if dict(sorted(categories.items())) != manifest.category_counts:
        raise ExperimentError("EXPERIMENT_BENCHMARK_CATEGORY_COUNT_MISMATCH")
    if dict(sorted(splits.items())) != manifest.split_counts:
        raise ExperimentError("EXPERIMENT_BENCHMARK_SPLIT_COUNT_MISMATCH")
    return benchmark, manifest


__all__ = [
    "Answerability",
    "BENCHMARK_SCHEMA_VERSION",
    "BENCHMARK_VERSION",
    "BenchmarkCase",
    "BenchmarkCategory",
    "BenchmarkFile",
    "BenchmarkManifest",
    "BenchmarkSplit",
    "COMPATIBLE_CORPUS_VERSION",
    "ObjectiveExpectedValue",
    "RUBRIC_VERSION",
    "ReferenceSource",
    "RequiredConstraint",
    "RequiredFact",
    "ScoringMetadata",
    "canonical_json_bytes",
    "load_and_verify_benchmark",
    "load_benchmark",
    "sha256_canonical",
    "sha256_file",
]
