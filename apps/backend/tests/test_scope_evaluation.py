from services.agent.scope_evaluation import (
    ScopeEvaluationRecord,
    summarize_scope_evaluation,
)
from services.agent.scope_guard import ScopeCategory, ScopeIntent


def test_scope_metrics_report_false_refusal_leakage_safety_latency_and_cost() -> None:
    records = [
        ScopeEvaluationRecord(
            ScopeCategory.IN_SCOPE_GENERAL_WELLNESS,
            ScopeCategory.OUT_OF_SCOPE,
            ScopeIntent.WEIGHT_MANAGEMENT,
            ScopeIntent.OUT_OF_SCOPE,
            10.0,
        ),
        ScopeEvaluationRecord(
            ScopeCategory.OUT_OF_SCOPE,
            ScopeCategory.IN_SCOPE_NUTRITION,
            ScopeIntent.OUT_OF_SCOPE,
            ScopeIntent.NUTRITION,
            20.0,
            1,
        ),
        ScopeEvaluationRecord(
            ScopeCategory.OUT_OF_SCOPE,
            ScopeCategory.OUT_OF_SCOPE,
            ScopeIntent.OUT_OF_SCOPE,
            ScopeIntent.OUT_OF_SCOPE,
            30.0,
        ),
        ScopeEvaluationRecord(
            ScopeCategory.SAFETY_ESCALATION,
            ScopeCategory.SAFETY_ESCALATION,
            ScopeIntent.SAFETY_ESCALATION,
            ScopeIntent.SAFETY_ESCALATION,
            40.0,
        ),
        ScopeEvaluationRecord(
            ScopeCategory.AMBIGUOUS,
            ScopeCategory.AMBIGUOUS,
            ScopeIntent.AMBIGUOUS,
            ScopeIntent.AMBIGUOUS,
            50.0,
            1,
        ),
    ]

    metrics = summarize_scope_evaluation(records, judge_cost_usd=0.002)

    assert metrics["sample_count"] == 5
    assert metrics["false_refusal_rate"] == 0.5
    assert metrics["oos_leakage_rate"] == 0.5
    assert metrics["oos_precision"] == 0.5
    assert metrics["oos_recall"] == 0.5
    assert metrics["oos_f1"] == 0.5
    assert metrics["ambiguous_accuracy"] == 1.0
    assert metrics["safety_recall"] == 1.0
    assert metrics["latency_ms_p50"] == 30.0
    assert metrics["latency_ms_p95"] == 50.0
    assert metrics["judge_calls_per_1000"] == 400.0
    assert metrics["estimated_judge_cost_usd"] == 0.004
