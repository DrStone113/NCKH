"""Deterministic authoring of calculation candidates for human review."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.agent.tools.tdee import calculate_tdee
from services.experiment.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    BenchmarkCase,
    BenchmarkCategory,
    BenchmarkSplit,
    ObjectiveExpectedValue,
    ReferenceSource,
    RequiredFact,
    ScoringMetadata,
    Answerability,
    canonical_json_bytes,
    sha256_canonical,
    sha256_file,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.models import ExperimentProfile
from services.experiment.records import repository_state
from services.nutrition.registry import POLICY_VERSION

CALCULATION_CANDIDATE_SCHEMA_VERSION = "1.0"
CALCULATION_CANDIDATE_GENERATOR_VERSION = "calculation-candidates-v1.0.0"
CALCULATION_CANDIDATE_STATUS = "DRAFT_REQUIRES_HUMAN_REVIEW"
EXPECTED_CALCULATION_CANDIDATE_COUNT = 60
POLICY_FILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "nutrition"
    / "nutrition_policy_v1_0_1.json"
)

_ACTIVITY_LABELS = {
    "sedentary": "ít vận động",
    "light": "vận động nhẹ",
    "moderate": "vận động vừa",
    "active": "vận động nhiều",
    "very_active": "vận động rất nhiều",
}
_GOAL_LABELS = {
    "lose_weight": "giảm cân",
    "maintain": "duy trì cân nặng",
    "gain_muscle": "tăng cơ",
}
_PROFILE_VARIANTS = {
    "male": (
        {"age": 22, "height_cm": 170.0, "weight_kg": 70.0},
        {"age": 45, "height_cm": 180.0, "weight_kg": 82.0},
    ),
    "female": (
        {"age": 24, "height_cm": 160.0, "weight_kg": 55.0},
        {"age": 50, "height_cm": 168.0, "weight_kg": 72.0},
    ),
}


class CalculationCandidate(BaseModel):
    """Runner-ineligible draft that wraps one proposed benchmark case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=r"^calc-draft-[0-9]{3}$")
    review_status: Literal["DRAFT_REQUIRES_HUMAN_REVIEW"]
    proposed_case: BenchmarkCase
    canonical_input: dict[str, Any]
    canonical_output_projection: dict[str, Any]
    canonical_output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    formula_ids: tuple[str, ...] = Field(min_length=1)
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_hash_and_identity(self) -> "CalculationCandidate":
        if self.proposed_case.case_id != self.candidate_id:
            raise ValueError("candidate and proposed case IDs must match")
        payload = self.model_dump(mode="json", exclude={"candidate_hash"})
        if sha256_canonical(payload) != self.candidate_hash:
            raise ValueError("candidate hash mismatch")
        return self


class CalculationCandidateFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    generator_version: str
    policy_version: str
    status: Literal["DRAFT_REQUIRES_HUMAN_REVIEW"]
    candidates: tuple[CalculationCandidate, ...]

    @model_validator(mode="after")
    def _validate_file(self) -> "CalculationCandidateFile":
        if self.schema_version != CALCULATION_CANDIDATE_SCHEMA_VERSION:
            raise ValueError("unsupported calculation candidate schema")
        if self.generator_version != CALCULATION_CANDIDATE_GENERATOR_VERSION:
            raise ValueError("unsupported calculation candidate generator")
        if self.policy_version != POLICY_VERSION:
            raise ValueError("calculation candidate policy mismatch")
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate IDs must be unique")
        if len(ids) != EXPECTED_CALCULATION_CANDIDATE_COUNT:
            raise ValueError("calculation candidate count must remain frozen at 60")
        return self


class CalculationCandidateManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    generator_version: str
    policy_version: str
    policy_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count: int = Field(ge=1)
    category_counts: dict[str, int]
    proposed_split_counts: dict[str, int]
    candidate_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_commit: str | None
    generation_worktree_clean: bool | None
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def _query(
    *,
    age: int,
    sex: str,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
) -> str:
    sex_label = "Nam" if sex == "male" else "Nữ"
    return (
        f"{sex_label} {age} tuổi, cao {height_cm:g} cm, nặng {weight_kg:g} kg, "
        f"mức hoạt động {_ACTIVITY_LABELS[activity_level]}, mục tiêu "
        f"{_GOAL_LABELS[goal]}. Hãy tính BMI, RMR theo Mifflin-St Jeor, "
        "TDEE và mức năng lượng mục tiêu mỗi ngày. "
        "Nêu rõ đây là các giá trị ước tính."
    )


def _expected_values(result: dict[str, Any]) -> tuple[ObjectiveExpectedValue, ...]:
    specifications = (
        (
            "bmi",
            "numerical_absolute_error",
            "bmi",
            "kg/m^2",
            0.1,
            ("BMI", "chỉ số khối cơ thể"),
        ),
        (
            "rmr",
            "numerical_absolute_error",
            "estimated_rmr_kcal_per_day",
            "kcal/day",
            10.0,
            ("RMR", "BMR", "chuyển hóa cơ bản"),
        ),
        (
            "tdee",
            "numerical_absolute_error",
            "estimated_tdee_kcal_per_day",
            "kcal/day",
            10.0,
            ("TDEE", "tổng năng lượng tiêu hao"),
        ),
        (
            "calorie-target",
            "calorie_target_error",
            "calorie_target_kcal_per_day",
            "kcal/day",
            10.0,
            ("mục tiêu calo", "mục tiêu kcal", "calo mục tiêu", "kcal/ngày"),
        ),
    )
    values = []
    for value_id, metric, key, unit, tolerance, labels in specifications:
        value = result.get(key)
        if not isinstance(value, (int, float)):
            raise ExperimentError("EXPERIMENT_CANDIDATE_EXPECTED_VALUE_MISSING", key)
        values.append(
            ObjectiveExpectedValue(
                value_id=value_id,
                metric=metric,
                expected=float(value),
                unit=unit,
                absolute_tolerance=tolerance,
                relative_tolerance=0.01,
                accepted_labels=labels,
            )
        )
    return tuple(values)


def _candidate(
    *,
    index: int,
    sex: str,
    variant: dict[str, float | int],
    activity_level: str,
    goal: str,
) -> CalculationCandidate:
    candidate_id = f"calc-draft-{index:03d}"
    canonical_input = {
        "user_id": candidate_id,
        "age": int(variant["age"]),
        "gender": sex,
        "equation_sex": sex,
        "height_cm": float(variant["height_cm"]),
        "weight_kg": float(variant["weight_kg"]),
        "activity_level": activity_level,
        "health_goal": goal,
        "dietary_restrictions": [],
    }
    result = calculate_tdee(canonical_input)
    if (
        result.get("policy_version") != POLICY_VERSION
        or result.get("status") != "READY"
        or result.get("calorie_target_status") != "AVAILABLE"
    ):
        raise ExperimentError("EXPERIMENT_CANDIDATE_NOT_READY", candidate_id)

    projection_keys = (
        "status",
        "bmi",
        "estimated_rmr_kcal_per_day",
        "estimated_tdee_kcal_per_day",
        "calorie_target_status",
        "calorie_target_kcal_per_day",
        "policy_version",
    )
    projection = {key: result[key] for key in projection_keys}
    formula_ids = tuple(str(value) for value in result["formula_ids"])
    profile = ExperimentProfile(
        profile_id=candidate_id,
        age=canonical_input["age"],
        sex=sex,
        height_cm=canonical_input["height_cm"],
        weight_kg=canonical_input["weight_kg"],
        activity_level=activity_level,
        goal=goal,
    )
    source_id = "nutrition-policy-v1.0.1"
    proposed_case = BenchmarkCase(
        case_id=candidate_id,
        category=BenchmarkCategory.ENERGY_CALCULATION,
        split=BenchmarkSplit.DEVELOPMENT,
        user_query=_query(
            age=canonical_input["age"],
            sex=sex,
            height_cm=canonical_input["height_cm"],
            weight_kg=canonical_input["weight_kg"],
            activity_level=activity_level,
            goal=goal,
        ),
        profile=profile,
        required_facts=(
            RequiredFact(
                fact_id="estimated-values-qualified",
                description="RMR and TDEE are presented as estimates.",
                acceptable_terms=("ước tính", "ước lượng", "estimated"),
                source_ids=(source_id,),
            ),
        ),
        required_constraints=(),
        reference_sources=(
            ReferenceSource(
                source_id=source_id,
                source_type="formula",
                title="Canonical nutrition formula registry",
                version=POLICY_VERSION,
            ),
        ),
        objective_expected_values=_expected_values(result),
        safety_flags=(),
        scoring_metadata=ScoringMetadata(
            answerability=Answerability.CALCULATION_BASED,
            research_questions=("RQ2",),
            objective_metrics=(
                "numerical_absolute_error",
                "calorie_target_error",
                "required_fact_coverage",
            ),
            human_rubrics=("factual_correctness", "completeness", "safety"),
            citation_required=False,
            notes=(
                "Draft generated from the canonical policy; requires human "
                "review before benchmark promotion."
            ),
        ),
    )
    base = {
        "candidate_id": candidate_id,
        "review_status": CALCULATION_CANDIDATE_STATUS,
        "proposed_case": proposed_case.model_dump(mode="json"),
        "canonical_input": canonical_input,
        "canonical_output_projection": projection,
        "canonical_output_hash": sha256_canonical(result),
        "formula_ids": formula_ids,
    }
    return CalculationCandidate.model_validate(
        {**base, "candidate_hash": sha256_canonical(base)}
    )


def build_calculation_candidates() -> CalculationCandidateFile:
    candidates = []
    index = 1
    for sex in ("male", "female"):
        for variant in _PROFILE_VARIANTS[sex]:
            for activity_level in _ACTIVITY_LABELS:
                for goal in _GOAL_LABELS:
                    candidates.append(
                        _candidate(
                            index=index,
                            sex=sex,
                            variant=variant,
                            activity_level=activity_level,
                            goal=goal,
                        )
                    )
                    index += 1
    return CalculationCandidateFile(
        schema_version=CALCULATION_CANDIDATE_SCHEMA_VERSION,
        generator_version=CALCULATION_CANDIDATE_GENERATOR_VERSION,
        policy_version=POLICY_VERSION,
        status=CALCULATION_CANDIDATE_STATUS,
        candidates=tuple(candidates),
    )


def review_template_bytes(candidates: Sequence[CalculationCandidate]) -> bytes:
    buffer = StringIO(newline="")
    fieldnames = (
        "candidate_id",
        "proposed_split",
        "query",
        "sex",
        "age",
        "height_cm",
        "weight_kg",
        "activity_level",
        "goal",
        "expected_bmi",
        "expected_rmr_kcal_day",
        "expected_tdee_kcal_day",
        "expected_target_kcal_day",
        "review_decision",
        "reviewer_id",
        "reviewer_notes",
    )
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for candidate in candidates:
        case = candidate.proposed_case
        expected = {
            value.value_id: value.expected
            for value in case.objective_expected_values
        }
        writer.writerow(
            {
                "candidate_id": candidate.candidate_id,
                "proposed_split": case.split.value,
                "query": case.user_query,
                "sex": case.profile.sex,
                "age": case.profile.age,
                "height_cm": case.profile.height_cm,
                "weight_kg": case.profile.weight_kg,
                "activity_level": case.profile.activity_level,
                "goal": case.profile.goal,
                "expected_bmi": expected["bmi"],
                "expected_rmr_kcal_day": expected["rmr"],
                "expected_tdee_kcal_day": expected["tdee"],
                "expected_target_kcal_day": expected["calorie-target"],
                "review_decision": "",
                "reviewer_id": "",
                "reviewer_notes": "",
            }
        )
    return buffer.getvalue().encode("utf-8-sig")


def _atomic_write(path: Path, content: bytes, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ExperimentError("EXPERIMENT_CANDIDATE_OUTPUT_EXISTS", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_calculation_candidate_pack(
    output_dir: Path,
    *,
    repo_root: Path,
    overwrite: bool = False,
) -> tuple[Path, Path, Path]:
    commit, clean = repository_state(repo_root)
    if clean is not True:
        raise ExperimentError("EXPERIMENT_CANDIDATE_REQUIRES_CLEAN_WORKTREE")

    candidate_file = build_calculation_candidates()
    candidate_path = output_dir / "nutrition_calculation_candidates_v1.json"
    review_path = output_dir / "nutrition_calculation_review_template_v1.csv"
    manifest_path = output_dir / "nutrition_calculation_candidates_v1.manifest.json"
    for path in (candidate_path, review_path, manifest_path):
        if path.exists() and not overwrite:
            raise ExperimentError("EXPERIMENT_CANDIDATE_OUTPUT_EXISTS", str(path))

    candidate_bytes = canonical_json_bytes(
        candidate_file.model_dump(mode="json"), indent=2
    )
    review_bytes = review_template_bytes(candidate_file.candidates)
    category_counts = Counter(
        candidate.proposed_case.category.value
        for candidate in candidate_file.candidates
    )
    split_counts = Counter(
        candidate.proposed_case.split.value
        for candidate in candidate_file.candidates
    )
    manifest_base = {
        "schema_version": CALCULATION_CANDIDATE_SCHEMA_VERSION,
        "generator_version": CALCULATION_CANDIDATE_GENERATOR_VERSION,
        "policy_version": POLICY_VERSION,
        "policy_file_sha256": sha256_file(POLICY_FILE_PATH),
        "candidate_count": len(candidate_file.candidates),
        "category_counts": dict(sorted(category_counts.items())),
        "proposed_split_counts": dict(sorted(split_counts.items())),
        "candidate_file_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "review_template_sha256": hashlib.sha256(review_bytes).hexdigest(),
        "generation_commit": commit,
        "generation_worktree_clean": clean,
    }
    manifest = CalculationCandidateManifest.model_validate(
        {**manifest_base, "manifest_hash": sha256_canonical(manifest_base)}
    )
    _atomic_write(candidate_path, candidate_bytes, overwrite=overwrite)
    _atomic_write(review_path, review_bytes, overwrite=overwrite)
    _atomic_write(
        manifest_path,
        canonical_json_bytes(manifest.model_dump(mode="json"), indent=2),
        overwrite=overwrite,
    )
    return candidate_path, manifest_path, review_path


def load_and_verify_calculation_candidate_pack(
    candidate_path: Path,
    manifest_path: Path,
    review_path: Path,
) -> tuple[CalculationCandidateFile, CalculationCandidateManifest]:
    try:
        candidate_file = CalculationCandidateFile.model_validate_json(
            candidate_path.read_text(encoding="utf-8")
        )
        manifest = CalculationCandidateManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ExperimentError(
            "EXPERIMENT_CANDIDATE_PACK_INVALID", safe_error_detail(exc)
        ) from exc

    payload = manifest.model_dump(mode="json")
    stored_hash = payload.pop("manifest_hash")
    category_counts = Counter(
        candidate.proposed_case.category.value
        for candidate in candidate_file.candidates
    )
    split_counts = Counter(
        candidate.proposed_case.split.value
        for candidate in candidate_file.candidates
    )
    checks = (
        sha256_canonical(payload) == stored_hash,
        sha256_file(candidate_path) == manifest.candidate_file_sha256,
        sha256_file(review_path) == manifest.review_template_sha256,
        sha256_file(POLICY_FILE_PATH) == manifest.policy_file_sha256,
        manifest.candidate_count == len(candidate_file.candidates),
        manifest.policy_version == candidate_file.policy_version,
        manifest.generator_version == candidate_file.generator_version,
        manifest.schema_version == candidate_file.schema_version,
        manifest.category_counts == dict(sorted(category_counts.items())),
        manifest.proposed_split_counts == dict(sorted(split_counts.items())),
    )
    if not all(checks):
        raise ExperimentError("EXPERIMENT_CANDIDATE_PACK_HASH_MISMATCH")
    return candidate_file, manifest


__all__ = [
    "CALCULATION_CANDIDATE_GENERATOR_VERSION",
    "CALCULATION_CANDIDATE_SCHEMA_VERSION",
    "CALCULATION_CANDIDATE_STATUS",
    "EXPECTED_CALCULATION_CANDIDATE_COUNT",
    "CalculationCandidate",
    "CalculationCandidateFile",
    "CalculationCandidateManifest",
    "build_calculation_candidates",
    "load_and_verify_calculation_candidate_pack",
    "review_template_bytes",
    "write_calculation_candidate_pack",
]
