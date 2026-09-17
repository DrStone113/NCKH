"""Auditable technical review for nutrition calculation candidates.

The reviewer deliberately re-implements the four reviewed calculations from
the versioned policy instead of calling the production calculator.  This
provides an independent implementation check while preserving the distinction
between policy-concordant benchmark gold and clinical ground truth.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.experiment.benchmark import canonical_json_bytes, sha256_canonical
from services.experiment.benchmark_authoring import (
    CalculationCandidate,
    CalculationCandidateFile,
    CalculationCandidateManifest,
    load_and_verify_calculation_candidate_pack,
)
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.records import repository_state
from services.nutrition.registry import POLICY

CALCULATION_REVIEW_SCHEMA_VERSION = "1.0"
CALCULATION_REVIEW_PROTOCOL_VERSION = "calculation-review-v1.0.0"
CALCULATION_REVIEW_STATUS = "AI_ASSISTED_TECHNICAL_REVIEW_COMPLETE"
CALCULATION_REVIEWER_KIND = "AI_ASSISTED_TECHNICAL_REVIEW"
CALCULATION_REVIEW_PROMOTION_SCOPE = "DEVELOPMENT_ONLY"

REVIEW_FIELDNAMES = (
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
IMMUTABLE_REVIEW_FIELDNAMES = REVIEW_FIELDNAMES[:13]
ALLOWED_REVIEW_DECISIONS = frozenset({"APPROVE", "REVISE", "REJECT"})

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
_EXPECTED_VALUE_SPEC = {
    "bmi": ("kg/m^2", 0.1, "numerical_absolute_error"),
    "rmr": ("kcal/day", 10.0, "numerical_absolute_error"),
    "tdee": ("kcal/day", 10.0, "numerical_absolute_error"),
    "calorie-target": ("kcal/day", 10.0, "calorie_target_error"),
}


class CalculationReviewSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    stable_identifier: str = Field(min_length=1)
    url: str = Field(min_length=1)
    review_scope: str = Field(min_length=1)


class CalculationReviewManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    review_protocol_version: str
    status: Literal["AI_ASSISTED_TECHNICAL_REVIEW_COMPLETE"]
    reviewer_id: str = Field(min_length=1)
    reviewer_kind: Literal["AI_ASSISTED_TECHNICAL_REVIEW"]
    reviewed_at: datetime
    human_domain_signoff: Literal[False]
    promotion_scope: Literal["DEVELOPMENT_ONLY"]
    development_promotion_eligible: bool
    source_candidate_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count: int = Field(ge=1)
    decision_counts: dict[str, int]
    independent_checks: tuple[str, ...] = Field(min_length=1)
    source_references: tuple[CalculationReviewSource, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    review_execution_commit: str | None
    review_execution_worktree_clean: bool | None
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_manifest(self) -> "CalculationReviewManifest":
        if self.schema_version != CALCULATION_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported calculation review schema")
        if self.review_protocol_version != CALCULATION_REVIEW_PROTOCOL_VERSION:
            raise ValueError("unsupported calculation review protocol")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        if sum(self.decision_counts.values()) != self.candidate_count:
            raise ValueError("review decision count mismatch")
        if self.development_promotion_eligible and self.decision_counts != {
            "APPROVE": self.candidate_count
        }:
            raise ValueError("development promotion requires unanimous approval")
        payload = self.model_dump(mode="json", exclude={"manifest_hash"})
        if sha256_canonical(payload) != self.manifest_hash:
            raise ValueError("calculation review manifest hash mismatch")
        return self


class IndependentCalculation(BaseModel):
    """Small typed result from the independent policy calculation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bmi: float
    rmr: float
    tdee: float
    calorie_target: float


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _round_half_up(value: Decimal, decimals: int) -> float:
    quantum = Decimal("1").scaleb(-decimals)
    return float(value.quantize(quantum, rounding=ROUND_HALF_UP))


def _independent_calculation(candidate: CalculationCandidate) -> IndependentCalculation:
    """Recalculate reviewed values without importing the production calculator."""

    inputs = candidate.canonical_input
    try:
        age = int(inputs["age"])
        sex = str(inputs["equation_sex"])
        height_cm = _decimal(inputs["height_cm"])
        weight_kg = _decimal(inputs["weight_kg"])
        activity_level = str(inputs["activity_level"])
        goal = str(inputs["health_goal"])
        activity_factor = _decimal(POLICY["activity"]["factors"][activity_level])
    except (KeyError, TypeError, ValueError) as exc:
        raise ExperimentError(
            "EXPERIMENT_REVIEW_INPUT_INVALID", safe_error_detail(exc)
        ) from exc

    if sex not in {"male", "female"} or goal not in _GOAL_LABELS:
        raise ExperimentError(
            "EXPERIMENT_REVIEW_INPUT_INVALID", candidate.candidate_id
        )
    sex_constant = Decimal("5") if sex == "male" else Decimal("-161")
    bmi_raw = weight_kg / ((height_cm / Decimal("100")) ** 2)
    rmr_raw = (
        Decimal("10") * weight_kg
        + Decimal("6.25") * height_cm
        - Decimal("5") * Decimal(age)
        + sex_constant
    )
    tdee_raw = rmr_raw * activity_factor
    adjustment_fraction = _decimal(POLICY["calories"]["adjustment_fraction"])
    if goal == "lose_weight":
        adjustment = -min(
            tdee_raw * adjustment_fraction,
            _decimal(POLICY["calories"]["loss_cap_kcal"]),
        )
    elif goal == "gain_muscle":
        adjustment = min(
            tdee_raw * adjustment_fraction,
            _decimal(POLICY["calories"]["gain_cap_kcal"]),
        )
    else:
        adjustment = Decimal("0")
    target_raw = tdee_raw + adjustment
    return IndependentCalculation(
        bmi=_round_half_up(
            bmi_raw, int(POLICY["rounding"]["bmi_storage_decimals"])
        ),
        rmr=_round_half_up(
            rmr_raw, int(POLICY["rounding"]["energy_storage_decimals"])
        ),
        tdee=_round_half_up(
            tdee_raw, int(POLICY["rounding"]["energy_storage_decimals"])
        ),
        calorie_target=_round_half_up(
            target_raw, int(POLICY["rounding"]["energy_storage_decimals"])
        ),
    )


def _expected_query(candidate: CalculationCandidate) -> str:
    inputs = candidate.canonical_input
    sex_label = "Nam" if inputs["equation_sex"] == "male" else "Nữ"
    return (
        f"{sex_label} {int(inputs['age'])} tuổi, "
        f"cao {float(inputs['height_cm']):g} cm, "
        f"nặng {float(inputs['weight_kg']):g} kg, "
        f"mức hoạt động {_ACTIVITY_LABELS[str(inputs['activity_level'])]}, "
        f"mục tiêu {_GOAL_LABELS[str(inputs['health_goal'])]}. "
        "Hãy tính BMI, RMR theo Mifflin-St Jeor, TDEE và mức năng lượng "
        "mục tiêu mỗi ngày. Nêu rõ đây là các giá trị ước tính."
    )


def independently_review_candidate(
    candidate: CalculationCandidate,
) -> IndependentCalculation:
    """Fail closed unless one candidate passes every technical review check."""

    case = candidate.proposed_case
    profile = case.profile
    inputs = candidate.canonical_input
    projection = candidate.canonical_output_projection
    calculated = _independent_calculation(candidate)

    if case.user_query != _expected_query(candidate):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_QUERY_MISMATCH", candidate.candidate_id
        )
    if any(marker in case.user_query for marker in ("Ã", "Ä", "Æ", "á»")):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_QUERY_ENCODING_INVALID", candidate.candidate_id
        )
    profile_checks = (
        case.case_id == candidate.candidate_id,
        case.split.value == "development",
        case.category.value == "energy_calculation",
        profile.age == inputs["age"],
        profile.sex == inputs["equation_sex"],
        profile.height_cm == inputs["height_cm"],
        profile.weight_kg == inputs["weight_kg"],
        profile.activity_level == inputs["activity_level"],
        profile.goal == inputs["health_goal"],
        int(POLICY["supported_age"]["minimum"])
        <= profile.age
        <= int(POLICY["supported_age"]["maximum"]),
        calculated.bmi >= float(POLICY["bmi"]["boundaries"][0]),
        calculated.calorie_target
        >= float(POLICY["calories"]["specialist_gate_kcal"]),
    )
    if not all(profile_checks):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_APPLICABILITY_MISMATCH", candidate.candidate_id
        )

    expected_values = {
        value.value_id: value for value in case.objective_expected_values
    }
    independently_expected = {
        "bmi": calculated.bmi,
        "rmr": calculated.rmr,
        "tdee": calculated.tdee,
        "calorie-target": calculated.calorie_target,
    }
    projection_expected = {
        "bmi": calculated.bmi,
        "estimated_rmr_kcal_per_day": calculated.rmr,
        "estimated_tdee_kcal_per_day": calculated.tdee,
        "calorie_target_kcal_per_day": calculated.calorie_target,
    }
    if any(projection.get(key) != value for key, value in projection_expected.items()):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_PROJECTION_MISMATCH", candidate.candidate_id
        )
    if set(expected_values) != set(_EXPECTED_VALUE_SPEC):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_EXPECTED_VALUES_INVALID", candidate.candidate_id
        )
    for value_id, expected in independently_expected.items():
        value = expected_values[value_id]
        unit, tolerance, metric = _EXPECTED_VALUE_SPEC[value_id]
        if (
            value.expected != expected
            or value.unit != unit
            or value.absolute_tolerance != tolerance
            or value.relative_tolerance != 0.01
            or value.metric != metric
        ):
            raise ExperimentError(
                "EXPERIMENT_REVIEW_EXPECTED_VALUES_INVALID",
                f"{candidate.candidate_id}:{value_id}",
            )

    required_formula_ids = {
        str(POLICY["bmi"]["formula_id"]),
        str(POLICY["rmr"]["formula_id"]),
        str(POLICY["activity"]["formula_id"]),
        str(POLICY["rounding"]["formula_id"]),
    }
    calorie_formula_key = {
        "lose_weight": "loss_formula_id",
        "maintain": "maintenance_formula_id",
        "gain_muscle": "gain_formula_id",
    }[profile.goal]
    required_formula_ids.add(str(POLICY["calories"][calorie_formula_key]))
    if not required_formula_ids.issubset(candidate.formula_ids):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_FORMULA_PROVENANCE_INVALID", candidate.candidate_id
        )
    if (
        projection.get("status") != "READY"
        or projection.get("calorie_target_status") != "AVAILABLE"
        or projection.get("policy_version") != candidate.proposed_case.reference_sources[0].version
        or case.scoring_metadata.research_questions != ("RQ2",)
        or not any(
            "ước tính" in term
            for fact in case.required_facts
            for term in fact.acceptable_terms
        )
    ):
        raise ExperimentError(
            "EXPERIMENT_REVIEW_METADATA_INVALID", candidate.candidate_id
        )
    return calculated


def _read_review_rows(path: Path) -> list[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(StringIO(text, newline=""))
        if tuple(reader.fieldnames or ()) != REVIEW_FIELDNAMES:
            raise ExperimentError("EXPERIMENT_REVIEW_COLUMNS_INVALID", str(path))
        rows = [dict(row) for row in reader]
    except ExperimentError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ExperimentError(
            "EXPERIMENT_REVIEW_CSV_INVALID", safe_error_detail(exc)
        ) from exc
    return rows


def _validate_review_rows(
    *,
    candidates: Sequence[CalculationCandidate],
    template_rows: Sequence[dict[str, str]],
    completed_rows: Sequence[dict[str, str]],
    reviewer_id: str,
) -> Counter[str]:
    if len(template_rows) != len(candidates) or len(completed_rows) != len(candidates):
        raise ExperimentError("EXPERIMENT_REVIEW_ROW_COUNT_MISMATCH")
    expected_ids = [candidate.candidate_id for candidate in candidates]
    if (
        [row["candidate_id"] for row in template_rows] != expected_ids
        or [row["candidate_id"] for row in completed_rows] != expected_ids
    ):
        raise ExperimentError("EXPERIMENT_REVIEW_CANDIDATE_ORDER_MISMATCH")

    decisions: Counter[str] = Counter()
    for candidate, template, completed in zip(
        candidates, template_rows, completed_rows, strict=True
    ):
        independently_review_candidate(candidate)
        if any(completed[field] != template[field] for field in IMMUTABLE_REVIEW_FIELDNAMES):
            raise ExperimentError(
                "EXPERIMENT_REVIEW_IMMUTABLE_FIELD_CHANGED", candidate.candidate_id
            )
        decision = completed["review_decision"].strip().upper()
        if decision not in ALLOWED_REVIEW_DECISIONS:
            raise ExperimentError(
                "EXPERIMENT_REVIEW_DECISION_INVALID", candidate.candidate_id
            )
        if completed["reviewer_id"].strip() != reviewer_id:
            raise ExperimentError(
                "EXPERIMENT_REVIEW_REVIEWER_MISMATCH", candidate.candidate_id
            )
        if not completed["reviewer_notes"].strip():
            raise ExperimentError(
                "EXPERIMENT_REVIEW_NOTES_REQUIRED", candidate.candidate_id
            )
        decisions[decision] += 1
    return decisions


def _completed_review_bytes(
    *,
    candidates: Sequence[CalculationCandidate],
    template_rows: Sequence[dict[str, str]],
    reviewer_id: str,
) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REVIEW_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for candidate, row in zip(candidates, template_rows, strict=True):
        calculated = independently_review_candidate(candidate)
        completed = dict(row)
        completed.update(
            {
                "review_decision": "APPROVE",
                "reviewer_id": reviewer_id,
                "reviewer_notes": (
                    "Đối chiếu độc lập đạt: query/profile khớp; "
                    f"BMI {calculated.bmi:g} kg/m^2; RMR {calculated.rmr:g}, "
                    f"TDEE {calculated.tdee:g}, target "
                    f"{calculated.calorie_target:g} kcal/ngày; đúng phạm vi "
                    "adult và được định tính là ước tính theo policy."
                ),
            }
        )
        writer.writerow(completed)
    return buffer.getvalue().encode("utf-8-sig")


def _source_references() -> tuple[CalculationReviewSource, ...]:
    return (
        CalculationReviewSource(
            source_id="mifflin-1990",
            title="A new predictive equation for resting energy expenditure in healthy individuals",
            stable_identifier="PMID:2305711; DOI:10.1093/ajcn/51.2.241",
            url="https://pubmed.ncbi.nlm.nih.gov/2305711/",
            review_scope="Existence and healthy-adult basis of the Mifflin-St Jeor RMR equation.",
        ),
        CalculationReviewSource(
            source_id="who-bmi-definition",
            title="WHO obesity and overweight fact sheet",
            stable_identifier="WHO fact sheet: obesity-and-overweight",
            url="https://www.who.int/news-room/fact-sheets/detail/obesity-and-overweight",
            review_scope="Adult BMI definition as weight in kilograms divided by height in metres squared.",
        ),
    )


def _atomic_write(path: Path, content: bytes, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ExperimentError("EXPERIMENT_REVIEW_OUTPUT_EXISTS", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_completed_calculation_review(
    *,
    candidate_path: Path,
    candidate_manifest_path: Path,
    review_template_path: Path,
    completed_review_path: Path,
    review_manifest_path: Path,
    repo_root: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Run the independent review and write a hash-bound completed register."""

    reviewer_id = reviewer_id.strip()
    if not reviewer_id:
        raise ExperimentError("EXPERIMENT_REVIEW_REVIEWER_REQUIRED")
    if reviewed_at.tzinfo is None:
        raise ExperimentError("EXPERIMENT_REVIEW_TIMEZONE_REQUIRED")
    commit, clean = repository_state(repo_root)
    if clean is not True:
        raise ExperimentError("EXPERIMENT_REVIEW_REQUIRES_CLEAN_WORKTREE")
    for path in (completed_review_path, review_manifest_path):
        if path.exists() and not overwrite:
            raise ExperimentError("EXPERIMENT_REVIEW_OUTPUT_EXISTS", str(path))

    candidate_file, candidate_manifest = load_and_verify_calculation_candidate_pack(
        candidate_path, candidate_manifest_path, review_template_path
    )
    template_rows = _read_review_rows(review_template_path)
    completed_bytes = _completed_review_bytes(
        candidates=candidate_file.candidates,
        template_rows=template_rows,
        reviewer_id=reviewer_id,
    )
    completed_hash = hashlib.sha256(completed_bytes).hexdigest()
    completed_text = completed_bytes.decode("utf-8-sig")
    completed_reader = csv.DictReader(StringIO(completed_text, newline=""))
    completed_rows = [dict(row) for row in completed_reader]
    decisions = _validate_review_rows(
        candidates=candidate_file.candidates,
        template_rows=template_rows,
        completed_rows=completed_rows,
        reviewer_id=reviewer_id,
    )
    manifest_base = {
        "schema_version": CALCULATION_REVIEW_SCHEMA_VERSION,
        "review_protocol_version": CALCULATION_REVIEW_PROTOCOL_VERSION,
        "status": CALCULATION_REVIEW_STATUS,
        "reviewer_id": reviewer_id,
        "reviewer_kind": CALCULATION_REVIEWER_KIND,
        "reviewed_at": reviewed_at,
        "human_domain_signoff": False,
        "promotion_scope": CALCULATION_REVIEW_PROMOTION_SCOPE,
        "development_promotion_eligible": decisions == {"APPROVE": len(completed_rows)},
        "source_candidate_manifest_hash": candidate_manifest.manifest_hash,
        "candidate_file_sha256": candidate_manifest.candidate_file_sha256,
        "review_template_sha256": candidate_manifest.review_template_sha256,
        "completed_review_sha256": completed_hash,
        "candidate_count": len(completed_rows),
        "decision_counts": dict(sorted(decisions.items())),
        "independent_checks": (
            "immutable CSV fields match the hash-bound source template",
            "query wording and all explicit inputs match the proposed profile",
            "BMI, Mifflin-St Jeor RMR, TDEE, and goal target were independently recalculated",
            "ROUND_HALF_UP storage precision, units, metrics, and tolerances match the policy",
            "all synthetic profiles remain inside adult, BMI, and minimum-energy applicability gates",
            "formula provenance, estimate qualifier, RQ2 mapping, and development split are present",
        ),
        "source_references": _source_references(),
        "limitations": (
            "This is an AI-assisted technical review, not a human clinician or independent domain-expert signoff.",
            "Approval establishes policy-concordant benchmark gold for RQ2, not universal clinical ground truth.",
            "Activity factors and calorie adjustments are versioned product-policy heuristics.",
            "The reviewed grid covers four synthetic adult profiles and does not cover safety or boundary cases.",
            "Approval permits development promotion only; pilot/final freeze requires an explicit later step.",
        ),
        "review_execution_commit": commit,
        "review_execution_worktree_clean": clean,
    }
    unsigned_manifest = CalculationReviewManifest.model_construct(
        **manifest_base,
        manifest_hash="0" * 64,
    )
    manifest_payload = unsigned_manifest.model_dump(
        mode="json", exclude={"manifest_hash"}
    )
    manifest = CalculationReviewManifest.model_validate(
        {
            **manifest_payload,
            "manifest_hash": sha256_canonical(manifest_payload),
        }
    )
    _atomic_write(completed_review_path, completed_bytes, overwrite=overwrite)
    _atomic_write(
        review_manifest_path,
        canonical_json_bytes(manifest.model_dump(mode="json"), indent=2),
        overwrite=overwrite,
    )
    return completed_review_path, review_manifest_path


def load_and_verify_completed_calculation_review(
    *,
    candidate_path: Path,
    candidate_manifest_path: Path,
    review_template_path: Path,
    completed_review_path: Path,
    review_manifest_path: Path,
) -> tuple[
    CalculationCandidateFile,
    CalculationCandidateManifest,
    CalculationReviewManifest,
]:
    """Verify source integrity, completed decisions, and independent arithmetic."""

    candidate_file, candidate_manifest = load_and_verify_calculation_candidate_pack(
        candidate_path, candidate_manifest_path, review_template_path
    )
    try:
        review_manifest = CalculationReviewManifest.model_validate_json(
            review_manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ExperimentError(
            "EXPERIMENT_REVIEW_MANIFEST_INVALID", safe_error_detail(exc)
        ) from exc
    template_rows = _read_review_rows(review_template_path)
    completed_rows = _read_review_rows(completed_review_path)
    decisions = _validate_review_rows(
        candidates=candidate_file.candidates,
        template_rows=template_rows,
        completed_rows=completed_rows,
        reviewer_id=review_manifest.reviewer_id,
    )
    checks = (
        review_manifest.source_candidate_manifest_hash
        == candidate_manifest.manifest_hash,
        review_manifest.candidate_file_sha256
        == candidate_manifest.candidate_file_sha256,
        review_manifest.review_template_sha256
        == candidate_manifest.review_template_sha256,
        review_manifest.completed_review_sha256
        == hashlib.sha256(completed_review_path.read_bytes()).hexdigest(),
        review_manifest.candidate_count == len(completed_rows),
        review_manifest.decision_counts == dict(sorted(decisions.items())),
        review_manifest.development_promotion_eligible
        == (decisions == {"APPROVE": len(completed_rows)}),
    )
    if not all(checks):
        raise ExperimentError("EXPERIMENT_REVIEW_INTEGRITY_MISMATCH")
    return candidate_file, candidate_manifest, review_manifest


__all__ = [
    "ALLOWED_REVIEW_DECISIONS",
    "CALCULATION_REVIEW_PROTOCOL_VERSION",
    "CALCULATION_REVIEW_SCHEMA_VERSION",
    "CALCULATION_REVIEW_STATUS",
    "CALCULATION_REVIEWER_KIND",
    "CalculationReviewManifest",
    "CalculationReviewSource",
    "IndependentCalculation",
    "independently_review_candidate",
    "load_and_verify_completed_calculation_review",
    "write_completed_calculation_review",
]
