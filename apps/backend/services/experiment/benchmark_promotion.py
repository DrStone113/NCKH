"""Promote unanimously reviewed calculation cases to a development benchmark."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from services.experiment.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    CALCULATION_DEVELOPMENT_BENCHMARK_VERSION,
    COMPATIBLE_CORPUS_VERSION,
    RUBRIC_VERSION,
    BenchmarkFile,
    BenchmarkManifest,
    BenchmarkPromotionProvenance,
    canonical_json_bytes,
    load_and_verify_benchmark,
    sha256_canonical,
)
from services.experiment.benchmark_review import (
    CALCULATION_REVIEW_STATUS,
    CALCULATION_REVIEWER_KIND,
    load_and_verify_completed_calculation_review,
)
from services.experiment.errors import ExperimentError
from services.experiment.records import repository_state

CALCULATION_PROMOTION_PIPELINE_VERSION = "calculation-promotion-v1.0.0"


def _atomic_write(path: Path, content: bytes, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ExperimentError("EXPERIMENT_PROMOTION_OUTPUT_EXISTS", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _reference_source_versions(benchmark: BenchmarkFile) -> dict[str, str]:
    versions: dict[str, str] = {}
    for case in benchmark.cases:
        for source in case.reference_sources:
            existing = versions.get(source.source_id)
            if existing is not None and existing != source.version:
                raise ExperimentError(
                    "EXPERIMENT_PROMOTION_REFERENCE_VERSION_CONFLICT",
                    source.source_id,
                )
            versions[source.source_id] = source.version
    return dict(sorted(versions.items()))


def write_calculation_development_benchmark(
    *,
    candidate_path: Path,
    candidate_manifest_path: Path,
    review_template_path: Path,
    completed_review_path: Path,
    review_manifest_path: Path,
    benchmark_path: Path,
    benchmark_manifest_path: Path,
    repo_root: Path,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Promote only a complete, unanimous, development-scoped review."""

    commit, clean = repository_state(repo_root)
    if clean is not True:
        raise ExperimentError("EXPERIMENT_PROMOTION_REQUIRES_CLEAN_WORKTREE")
    for path in (benchmark_path, benchmark_manifest_path):
        if path.exists() and not overwrite:
            raise ExperimentError("EXPERIMENT_PROMOTION_OUTPUT_EXISTS", str(path))

    candidate_file, candidate_manifest, review_manifest = (
        load_and_verify_completed_calculation_review(
            candidate_path=candidate_path,
            candidate_manifest_path=candidate_manifest_path,
            review_template_path=review_template_path,
            completed_review_path=completed_review_path,
            review_manifest_path=review_manifest_path,
        )
    )
    candidate_count = len(candidate_file.candidates)
    if (
        review_manifest.status != CALCULATION_REVIEW_STATUS
        or review_manifest.reviewer_kind != CALCULATION_REVIEWER_KIND
        or review_manifest.promotion_scope != "DEVELOPMENT_ONLY"
        or review_manifest.decision_counts != {"APPROVE": candidate_count}
        or review_manifest.development_promotion_eligible is not True
    ):
        raise ExperimentError("EXPERIMENT_PROMOTION_REVIEW_NOT_ELIGIBLE")

    benchmark = BenchmarkFile(
        benchmark_version=CALCULATION_DEVELOPMENT_BENCHMARK_VERSION,
        schema_version=BENCHMARK_SCHEMA_VERSION,
        cases=tuple(
            candidate.proposed_case for candidate in candidate_file.candidates
        ),
    )
    benchmark_bytes = canonical_json_bytes(
        benchmark.model_dump(mode="json"), indent=2
    )
    category_counts = Counter(case.category.value for case in benchmark.cases)
    split_counts = Counter(case.split.value for case in benchmark.cases)
    provenance = BenchmarkPromotionProvenance(
        promotion_pipeline_version=CALCULATION_PROMOTION_PIPELINE_VERSION,
        promotion_scope="DEVELOPMENT_ONLY",
        source_candidate_manifest_hash=candidate_manifest.manifest_hash,
        source_review_manifest_hash=review_manifest.manifest_hash,
        source_completed_review_sha256=review_manifest.completed_review_sha256,
        review_protocol_version=review_manifest.review_protocol_version,
        review_status=review_manifest.status,
        reviewer_kind=review_manifest.reviewer_kind,
        human_domain_signoff=review_manifest.human_domain_signoff,
        source_candidate_count=candidate_count,
        approved_candidate_count=review_manifest.decision_counts["APPROVE"],
    )
    manifest_base = {
        "benchmark_version": benchmark.benchmark_version,
        "schema_version": benchmark.schema_version,
        "case_count": len(benchmark.cases),
        "category_counts": dict(sorted(category_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "benchmark_file_sha256": hashlib.sha256(benchmark_bytes).hexdigest(),
        "creation_commit": commit,
        "creation_worktree_clean": clean,
        "rubric_version": RUBRIC_VERSION,
        "reference_source_versions": _reference_source_versions(benchmark),
        "corpus_version": COMPATIBLE_CORPUS_VERSION,
        "promotion_provenance": provenance,
    }
    unsigned_manifest = BenchmarkManifest.model_construct(
        **manifest_base,
        manifest_hash="0" * 64,
    )
    manifest_payload = unsigned_manifest.model_dump(
        mode="json", exclude={"manifest_hash"}
    )
    manifest = BenchmarkManifest.model_validate(
        {
            **manifest_payload,
            "manifest_hash": sha256_canonical(manifest_payload),
        }
    )
    _atomic_write(benchmark_path, benchmark_bytes, overwrite=overwrite)
    _atomic_write(
        benchmark_manifest_path,
        canonical_json_bytes(manifest.model_dump(mode="json"), indent=2),
        overwrite=overwrite,
    )
    return benchmark_path, benchmark_manifest_path


def load_and_verify_promoted_calculation_benchmark(
    *,
    candidate_path: Path,
    candidate_manifest_path: Path,
    review_template_path: Path,
    completed_review_path: Path,
    review_manifest_path: Path,
    benchmark_path: Path,
    benchmark_manifest_path: Path,
) -> tuple[BenchmarkFile, BenchmarkManifest]:
    """Verify both ordinary benchmark integrity and its complete review chain."""

    candidate_file, candidate_manifest, review_manifest = (
        load_and_verify_completed_calculation_review(
            candidate_path=candidate_path,
            candidate_manifest_path=candidate_manifest_path,
            review_template_path=review_template_path,
            completed_review_path=completed_review_path,
            review_manifest_path=review_manifest_path,
        )
    )
    benchmark, manifest = load_and_verify_benchmark(
        benchmark_path, benchmark_manifest_path
    )
    provenance = manifest.promotion_provenance
    checks = (
        benchmark.benchmark_version
        == CALCULATION_DEVELOPMENT_BENCHMARK_VERSION,
        tuple(candidate.proposed_case for candidate in candidate_file.candidates)
        == benchmark.cases,
        provenance is not None,
        provenance is not None
        and provenance.promotion_pipeline_version
        == CALCULATION_PROMOTION_PIPELINE_VERSION,
        provenance is not None
        and provenance.source_candidate_manifest_hash
        == candidate_manifest.manifest_hash,
        provenance is not None
        and provenance.source_review_manifest_hash == review_manifest.manifest_hash,
        provenance is not None
        and provenance.source_completed_review_sha256
        == review_manifest.completed_review_sha256,
        provenance is not None
        and provenance.review_protocol_version
        == review_manifest.review_protocol_version,
        provenance is not None
        and provenance.approved_candidate_count == len(benchmark.cases),
        review_manifest.decision_counts == {"APPROVE": len(benchmark.cases)},
    )
    if not all(checks):
        raise ExperimentError("EXPERIMENT_PROMOTION_PROVENANCE_MISMATCH")
    return benchmark, manifest


__all__ = [
    "CALCULATION_PROMOTION_PIPELINE_VERSION",
    "load_and_verify_promoted_calculation_benchmark",
    "write_calculation_development_benchmark",
]
