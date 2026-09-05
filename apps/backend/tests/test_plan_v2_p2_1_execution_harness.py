from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

from services.acceptance.p2_1.execution import (
    AcceptanceCaseLoader,
    CaseExecutionContext,
    ExecutionCaseView,
    LegacyPlanReadOnlyExecutor,
    PlanV2Executor,
    normalize_for_comparator,
)


def _view() -> ExecutionCaseView:
    return ExecutionCaseView(
        case_id="development-harness-001",
        category="nutrition",
        prompt="Create a one-day planned menu only.",
        fixture={"prompt_facts": "authoritative", "unstated_context": "UNKNOWN"},
    )


def _context(*, known_profile: bool = False) -> CaseExecutionContext:
    profile = {"user_id": "development-harness-owner"}
    if known_profile:
        profile.update({
            "age": 30, "equation_sex": "female", "height_cm": 165,
            "weight_kg": 58, "activity_level": "light", "health_goal": "maintain",
        })
    return CaseExecutionContext(
        case_id="development-harness-001", owner_user_id="development-harness-owner", session_id="dev-session",
        period_start="2026-10-01", period_end="2026-10-01", timezone="Asia/Ho_Chi_Minh",
        profile_fixture=profile, plan_state_fixture={}, nutrition_state_fixture={}, training_state_fixture={},
    )


def test_case_loader_projects_no_oracle_fields(tmp_path: Path):
    holdout = {
        "cases": [{
            "case_id": "dev-1", "category": "nutrition", "prompt": "Plan safely", "fixture": {"x": "y"},
            "oracle_profile": "IMPOSSIBLE_EXPECTED_ANSWER", "deterministic_check_ids": ["must_not_leak"],
        }]
    }
    path = tmp_path / "development-holdout.json"
    path.write_text(json.dumps(holdout), encoding="utf-8")
    case = AcceptanceCaseLoader(str(path)).execution_cases()[0]
    assert case.prompt == "Plan safely"
    assert not hasattr(case, "oracle_profile")
    assert "IMPOSSIBLE_EXPECTED_ANSWER" not in repr(case)


def test_execution_module_has_static_oracle_firewall():
    source = Path(__file__).resolve().parents[1] / "services" / "acceptance" / "p2_1" / "execution.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("scoring" in name.casefold() or "oracle" in name.casefold() for name in imported)


def test_plan_v2_executor_uses_actual_entrypoint_for_clarification_and_ready():
    executor = PlanV2Executor()
    clarification = asyncio.run(executor.execute(_view(), _context()))
    ready = asyncio.run(executor.execute(_view(), _context(known_profile=True)))

    assert clarification.executor == "PLAN_V2"
    assert clarification.status == "CLARIFICATION_REQUIRED"
    assert ready.status == "READY"
    assert not clarification.captured_write_attempts
    assert not ready.captured_write_attempts


def test_oracle_sentinel_does_not_change_executor_observation(tmp_path: Path):
    base = {"case_id": "dev-2", "category": "nutrition", "prompt": "Plan safely", "fixture": {}}
    first = {"cases": [{**base, "oracle_profile": "IMPOSSIBLE_A"}]}
    second = {"cases": [{**base, "oracle_profile": "IMPOSSIBLE_B"}]}
    first_path, second_path = tmp_path / "first.json", tmp_path / "second.json"
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path.write_text(json.dumps(second), encoding="utf-8")
    executor = PlanV2Executor()
    output_a = asyncio.run(executor.execute(AcceptanceCaseLoader(str(first_path)).execution_cases()[0], _context()))
    output_b = asyncio.run(executor.execute(AcceptanceCaseLoader(str(second_path)).execution_cases()[0], _context()))
    assert output_a.status == output_b.status == "CLARIFICATION_REQUIRED"
    # Plan revisions are intentionally assigned fresh IDs/timestamps.  Compare
    # the oracle-blind behavior rather than incidental persistence identity.
    projection_a = {
        "status": output_a.status,
        "clarification": output_a.clarification,
        "refusal": output_a.refusal,
        "intended_actions": output_a.intended_actions,
        "captured_write_attempts": output_a.captured_write_attempts,
        "errors": output_a.errors,
        "validation_status": output_a.normalized_output["validation"]["status"],
        "validation_issue_codes": tuple(issue["code"] for issue in output_a.normalized_output["validation"]["issues"]),
    }
    projection_b = {
        "status": output_b.status,
        "clarification": output_b.clarification,
        "refusal": output_b.refusal,
        "intended_actions": output_b.intended_actions,
        "captured_write_attempts": output_b.captured_write_attempts,
        "errors": output_b.errors,
        "validation_status": output_b.normalized_output["validation"]["status"],
        "validation_issue_codes": tuple(issue["code"] for issue in output_b.normalized_output["validation"]["issues"]),
    }
    assert projection_a == projection_b


class _DevelopmentRollbackSession:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement, _params=None):
        self.executed.append(str(statement))

    async def rollback(self):
        self.rolled_back = True


def test_legacy_adapter_captures_and_rolls_back_write_attempt():
    session = _DevelopmentRollbackSession()
    executor = LegacyPlanReadOnlyExecutor(lambda: session)
    result = asyncio.run(executor.execute(_view(), _context()))
    assert result.status == "READY"
    assert result.captured_write_attempts == ("LEGACY_INSERT_ROLLED_BACK",)
    assert session.rolled_back
    assert any("INSERT INTO plans" in sql for sql in session.executed)
    normalized = normalize_for_comparator(result)
    assert normalized is not None
    assert normalized["unintended_writes"] is False


def test_legacy_adapter_marks_missing_equivalent_not_comparable():
    case = ExecutionCaseView("dev-combined", "combined_health", "combine", {})
    result = asyncio.run(LegacyPlanReadOnlyExecutor(lambda: _DevelopmentRollbackSession()).execute(case, _context()))
    assert result.status == "NOT_COMPARABLE"
    assert result.not_comparable_reason == "LEGACY_HAS_NO_READ_ONLY_COMBINED_OR_VERSIONED_LIFECYCLE_ENTRYPOINT"
