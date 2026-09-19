from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

from services.experiment.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    SINGLE_TURN_DEVELOPMENT_BENCHMARK_VERSION,
    BenchmarkCategory,
    BenchmarkFile,
)
from services.experiment.single_turn_benchmark import (
    EXPECTED_SINGLE_TURN_COUNT,
    build_single_turn_candidates,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CALCULATION_DIR = (
    BACKEND_ROOT / "data" / "research" / "benchmarks" / "calculation_development_v1"
)


@lru_cache(maxsize=1)
def _candidates():
    candidate_file, _, _ = build_single_turn_candidates(
        calculation_benchmark_path=CALCULATION_DIR
        / "nutrition_calculation_development_v1.json",
        calculation_manifest_path=CALCULATION_DIR
        / "nutrition_calculation_development_v1.manifest.json",
    )
    return candidate_file.candidates


def test_single_turn_candidate_design_has_frozen_counts_and_provenance() -> None:
    candidates = _candidates()
    counts = Counter(candidate.proposed_case.category for candidate in candidates)

    assert len(candidates) == EXPECTED_SINGLE_TURN_COUNT
    assert counts == {
        BenchmarkCategory.ENERGY_CALCULATION: 60,
        BenchmarkCategory.RAG_KNOWLEDGE_QUESTIONS: 100,
        BenchmarkCategory.PERSONALIZED_RECOMMENDATION: 80,
        BenchmarkCategory.SAFETY_BOUNDARY_CASES: 30,
    }
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)
    assert all(candidate.proposed_case.split.value == "development" for candidate in candidates)
    benchmark = BenchmarkFile(
        benchmark_version=SINGLE_TURN_DEVELOPMENT_BENCHMARK_VERSION,
        schema_version=BENCHMARK_SCHEMA_VERSION,
        cases=tuple(candidate.proposed_case for candidate in candidates),
    )
    assert len(benchmark.cases) == EXPECTED_SINGLE_TURN_COUNT


def test_knowledge_cases_bind_gold_facts_to_frozen_corpus_coordinates() -> None:
    knowledge = [
        candidate.proposed_case
        for candidate in _candidates()
        if candidate.proposed_case.category
        == BenchmarkCategory.RAG_KNOWLEDGE_QUESTIONS
    ]

    assert len(knowledge) == 100
    assert all(case.scoring_metadata.citation_required for case in knowledge)
    assert all(case.required_facts for case in knowledge)
    assert all(
        source.source_type == "frozen_corpus_record"
        and source.corpus_version == "offline-v1-636"
        and source.dataset_file
        and source.source_record_id
        and source.content_hash
        for case in knowledge
        for source in case.reference_sources
    )


def test_personalization_cases_are_hidden_profile_pairs() -> None:
    personalized = [
        candidate.proposed_case
        for candidate in _candidates()
        if candidate.proposed_case.category
        == BenchmarkCategory.PERSONALIZED_RECOMMENDATION
    ]

    assert len(personalized) == 80
    for offset in range(0, len(personalized), 2):
        first, second = personalized[offset : offset + 2]
        assert first.user_query == second.user_query
        assert first.profile != second.profile
        assert first.profile.goal != second.profile.goal
        assert first.objective_expected_values[0].value_id == "calorie-target"
        assert second.objective_expected_values[0].value_id == "calorie-target"
    assert all(case.required_constraints for case in personalized)
    assert all(
        str(case.profile.age) not in case.user_query
        and f"{case.profile.weight_kg:g}" not in case.user_query
        and f"{case.profile.height_cm:g}" not in case.user_query
        for case in personalized
    )


def test_safety_cases_have_explicit_term_scored_boundaries() -> None:
    safety = [
        candidate.proposed_case
        for candidate in _candidates()
        if candidate.proposed_case.category == BenchmarkCategory.SAFETY_BOUNDARY_CASES
    ]

    assert len(safety) == 30
    assert all(case.safety_flags for case in safety)
    assert all(
        len(case.required_constraints) == 1
        and case.required_constraints[0].constraint_type == "safety_boundary"
        and case.required_constraints[0].required_terms
        for case in safety
    )
