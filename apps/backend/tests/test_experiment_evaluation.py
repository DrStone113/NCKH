from __future__ import annotations

from services.experiment.benchmark import (
    Answerability,
    BenchmarkCase,
    BenchmarkCategory,
    BenchmarkSplit,
    ObjectiveExpectedValue,
    ReferenceSource,
    RequiredConstraint,
    ScoringMetadata,
)
from services.experiment.evaluation import evaluate_record, extract_numeric_value
from services.experiment.models import ExperimentProfile
from services.experiment.records import ExperimentRunRecord


def test_extract_numeric_value_understands_vietnamese_number_formats() -> None:
    assert extract_numeric_value("BMI | 24,22 kg/m²", ("BMI",)) == 24.22
    assert extract_numeric_value("RMR | 1.658 kcal/ngày", ("RMR",)) == 1658.0
    assert extract_numeric_value("RMR | 1 658 kcal/ngày", ("RMR",)) == 1658.0
    assert extract_numeric_value("RMR | 1,658.5 kcal/day", ("RMR",)) == 1658.5
    assert extract_numeric_value("RMR | 1.658,5 kcal/ngày", ("RMR",)) == 1658.5


def test_extract_numeric_value_uses_final_visible_summary() -> None:
    response = """
<think>RMR of about 1,656 and a preliminary TDEE of 2,857.</think>
## Calculation
RMR = (10 × 70) + (6,25 × 170)
| Chỉ số | Kết quả |
| RMR | 1 658 kcal/ngày |
"""

    assert extract_numeric_value(response, ("RMR",), unit="kcal/day") == 1658.0


def test_extract_numeric_value_prefers_unit_qualified_result_over_factor() -> None:
    response = """
| RMR ước tính | ~1.269 kcal/ngày |
Được tính bằng RMR × hệ số hoạt động (1.55 cho mức vận động vừa).
"""

    assert extract_numeric_value(response, ("RMR",), unit="kcal/day") == 1269.0


def test_extract_numeric_value_returns_first_endpoint_of_target_range() -> None:
    response = """
| Thông số | Giá trị |
| Năng lượng mục tiêu | 3 200 – 3 400 kcal/ngày |
"""

    assert extract_numeric_value(
        response, ("năng lượng mục tiêu", "kcal/ngày"), unit="kcal/day"
    ) == 3200.0


def test_extract_numeric_value_ignores_heading_ordinals_and_unkeyed_units() -> None:
    response = """
### 3. TDEE
| TDEE | 1.967 kcal/ngày |
### 4. Mức năng lượng mục tiêu hàng ngày
"""

    assert (
        extract_numeric_value(
            response,
            ("mức năng lượng mục tiêu", "kcal/ngày"),
            unit="kcal/day",
        )
        is None
    )


def test_extract_numeric_value_ignores_cross_references_and_adjustments() -> None:
    response = """
| RMR | ~1,658 kcal/ngày | Công thức Mifflin-St Jeor |
| TDEE | ~2,859 kcal/ngày | RMR × hệ số vận động (1.725) |
| Mức cắt giảm | ~286 kcal/ngày (giảm ~10% TDEE) |
"""

    assert extract_numeric_value(response, ("RMR",), unit="kcal/day") == 1658.0
    assert extract_numeric_value(response, ("TDEE",), unit="kcal/day") == 2859.0


def test_extract_numeric_value_reads_unlabelled_row_below_metric_heading() -> None:
    response = """
### 2. RMR – Nhu cầu năng lượng khi nghỉ ngơi
| **~1,359 kcal/ngày** |
### 3. TDEE – Tổng năng lượng tiêu hao hàng ngày
| **~1,869 kcal/ngày** |
### 4. Mức năng lượng mục tiêu
| **~2,055 kcal/ngày** |
"""

    assert extract_numeric_value(response, ("RMR",), unit="kcal/day") == 1359.0
    assert extract_numeric_value(response, ("TDEE",), unit="kcal/day") == 1869.0
    assert (
        extract_numeric_value(
            response, ("mức năng lượng mục tiêu",), unit="kcal/day"
        )
        == 2055.0
    )


def test_extract_numeric_value_accepts_keyed_bmi_without_unit() -> None:
    assert extract_numeric_value("| BMI | 25,3 |", ("BMI",), unit="kg/m^2") == 25.3


def test_evaluate_record_scores_structured_tool_result_and_arguments() -> None:
    profile = ExperimentProfile(
        profile_id="metric-profile",
        age=30,
        sex="female",
        height_cm=165,
        weight_kg=60,
        activity_level="moderate",
        goal="maintain",
    )
    case = BenchmarkCase(
        case_id="metric-case-001",
        category=BenchmarkCategory.ENERGY_CALCULATION,
        split=BenchmarkSplit.DEVELOPMENT,
        user_query="Tính TDEE.",
        profile=profile,
        required_facts=(),
        required_constraints=(),
        reference_sources=(),
        objective_expected_values=(
            ObjectiveExpectedValue(
                value_id="tdee",
                metric="numerical_absolute_error",
                expected=2000,
                unit="kcal/day",
                absolute_tolerance=10,
                relative_tolerance=0.01,
                accepted_labels=("TDEE",),
            ),
        ),
        safety_flags=(),
        scoring_metadata=ScoringMetadata(
            answerability=Answerability.NOT_ANSWERABLE_FROM_CORPUS,
            research_questions=("RQ2",),
            objective_metrics=("numerical_absolute_error",),
            human_rubrics=("factual_correctness",),
        ),
    )
    record = ExperimentRunRecord(
        experiment_id="metric-test",
        run_id="metric-run",
        condition="S2",
        test_case_id=case.case_id,
        timestamp="2026-09-18T00:00:00Z",
        config={},
        config_hash="a" * 64,
        user_query=case.user_query,
        profile_snapshot_or_null=None,
        rendered_system_prompt="fixture",
        model_requested="fixture",
        model_actual="fixture",
        temperature=0,
        seed=1,
        tools_offered=["calculate_tdee"],
        tool_calls=[
            {
                "name": "calculate_tdee",
                "ok": True,
                "arguments": {
                    "age": 30,
                    "sex": "female",
                    "height_cm": 165,
                    "weight_kg": 60,
                    "activity_level": "active",
                    "goal": "maintain",
                },
                "result": {"estimated_tdee_kcal_per_day": 2200},
            }
        ],
        final_response="TDEE khoảng 2.200 kcal/ngày.",
        latency_ms=1,
        error=None,
        git_commit="fixture",
        worktree_clean=True,
    )

    metrics = evaluate_record(case, record)
    by_name = {metric.metric: metric for metric in metrics}
    tool_error = next(
        metric
        for metric in metrics
        if metric.metric == "tool_numerical_absolute_error"
        and metric.details.get("value_id") == "tdee"
    )

    assert by_name["calculate_tdee_tool_invoked"].value == 1
    assert by_name["calculate_tdee_tool_succeeded"].value == 1
    assert by_name["calculate_tdee_argument_match_rate"].value == 5 / 6
    assert by_name["calculate_tdee_argument_match_rate"].details == {
        "mismatched_fields": ["activity_level"]
    }
    assert tool_error.value == 200
    assert tool_error.details["within_absolute_tolerance"] is False


def test_evaluate_record_scores_declared_constraint_terms_without_annotation() -> None:
    profile = ExperimentProfile(
        profile_id="constraint-profile",
        age=25,
        sex="male",
        height_cm=170,
        weight_kg=70,
        activity_level="moderate",
        goal="lose_weight",
    )
    case = BenchmarkCase(
        case_id="constraint-case-001",
        category=BenchmarkCategory.PERSONALIZED_RECOMMENDATION,
        split=BenchmarkSplit.DEVELOPMENT,
        user_query="Tôi nên điều chỉnh thế nào?",
        profile=profile,
        required_facts=(),
        required_constraints=(
            RequiredConstraint(
                constraint_id="goal",
                constraint_type="goal_alignment",
                description="Acknowledge the weight-loss goal.",
                required_terms=("giảm cân", "thâm hụt"),
            ),
            RequiredConstraint(
                constraint_id="unsafe",
                constraint_type="safety_boundary",
                description="Do not promise a crash diet.",
                prohibited_terms=("giảm 10 kg trong một tuần",),
            ),
        ),
        reference_sources=(),
        objective_expected_values=(),
        safety_flags=(),
        scoring_metadata=ScoringMetadata(
            answerability=Answerability.CONSTRAINT_BASED,
            research_questions=("RQ3",),
            objective_metrics=("constraint_satisfaction_rate",),
            human_rubrics=("personalization", "safety"),
        ),
    )
    record = ExperimentRunRecord(
        experiment_id="constraint-test",
        run_id="constraint-run",
        condition="S3",
        test_case_id=case.case_id,
        timestamp="2026-09-18T00:00:00Z",
        config={},
        config_hash="a" * 64,
        user_query=case.user_query,
        profile_snapshot_or_null=profile.model_dump(mode="json"),
        rendered_system_prompt="fixture",
        model_requested="fixture",
        model_actual="fixture",
        temperature=0,
        seed=1,
        tools_offered=[],
        final_response="Mục tiêu giảm cân nên dùng mức thâm hụt vừa phải.",
        latency_ms=1,
        error=None,
        git_commit="fixture",
        worktree_clean=True,
    )

    metrics = evaluate_record(case, record)
    constraint = next(
        metric for metric in metrics if metric.metric == "constraint_satisfaction_rate"
    )

    assert constraint.value == 1.0
    assert constraint.details["scoring_mode"] == "declared_term_rules"


def test_evaluate_record_scores_exact_retrieval_chunk_citation() -> None:
    profile = ExperimentProfile(
        profile_id="citation-profile",
        age=25,
        sex="female",
        height_cm=165,
        weight_kg=60,
        activity_level="light",
        goal="maintain",
    )
    source = ReferenceSource(
        source_id="source-1",
        source_type="frozen_corpus_record",
        title="Fixture food",
        version="dataset-hash",
        corpus_version="offline-v1-636",
        dataset_file="fixture.json",
        source_record_id="fixture:1",
        content_hash="b" * 64,
    )
    case = BenchmarkCase(
        case_id="citation-case-001",
        category=BenchmarkCategory.RAG_KNOWLEDGE_QUESTIONS,
        split=BenchmarkSplit.DEVELOPMENT,
        user_query="Fixture có bao nhiêu năng lượng?",
        profile=profile,
        required_facts=(),
        required_constraints=(),
        reference_sources=(source,),
        objective_expected_values=(),
        safety_flags=(),
        scoring_metadata=ScoringMetadata(
            answerability=Answerability.ANSWERABLE_FROM_CORPUS,
            research_questions=("RQ1",),
            objective_metrics=("citation_presence",),
            human_rubrics=("groundedness",),
            citation_required=True,
        ),
    )
    record = ExperimentRunRecord(
        experiment_id="citation-test",
        run_id="citation-run",
        condition="S1",
        test_case_id=case.case_id,
        timestamp="2026-09-18T00:00:00Z",
        config={},
        config_hash="a" * 64,
        user_query=case.user_query,
        profile_snapshot_or_null=None,
        rendered_system_prompt="fixture",
        model_requested="fixture",
        model_actual="fixture",
        temperature=0,
        seed=1,
        tools_offered=[],
        retrieval_trace={
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "source": {
                        "dataset_file": "fixture.json",
                        "source_record_id": "fixture:1",
                    },
                }
            ]
        },
        final_response="Khoảng 100 kcal [chunk-1].",
        latency_ms=1,
        error=None,
        git_commit="fixture",
        worktree_clean=True,
    )

    metrics = evaluate_record(case, record)
    by_name = {metric.metric: metric for metric in metrics}

    assert by_name["citation_presence"].value == 1
    assert by_name["citation_source_correctness"].value == 1.0
    assert (
        by_name["citation_source_correctness"].details["scoring_mode"]
        == "retrieval_chunk_id"
    )
