"""Evaluate the frozen server semantic routing holdout without modifying it.

This is an engineering harness, not a production endpoint.  It intentionally
reports C as unavailable unless an actual configured server model is supplied;
no fake adapter may be used for C.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from config import settings
from services.agent.semantic_router_service import SemanticRouterService
from services.agent.turn_intent import classify_turn_intent, normalize_turn_text


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "server_semantic_routing_holdout_v1.json"


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _metrics(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(predictions)
    correct = sum(item["actual"] == item["expected"] for item in predictions)
    health_cases = [item for item in predictions if item["health_expected"]]
    health_recalled = sum(bool(item["health_actual"]) for item in health_cases)
    ambiguous_non_cases = [item for item in predictions if not item["clarification_expected"]]
    false_ambiguity = sum(item["clarification_actual"] for item in ambiguous_non_cases)
    negated_cases = [item for item in predictions if item["negated_expected"]]
    false_write = sum(
        item["write_actual"] is not None for item in negated_cases
    )
    critical_health = [item for item in predictions if item["id"] in {"H055", "H056", "H119", "H120"}]
    critical_miss = sum(not item["health_actual"] for item in critical_health)
    return {
        "case_count": total,
        "primary_intent_accuracy": correct / total if total else 0.0,
        "health_routing_recall": health_recalled / len(health_cases) if health_cases else 0.0,
        "false_ambiguity_rate": false_ambiguity / len(ambiguous_non_cases) if ambiguous_non_cases else 0.0,
        "false_positive_write_intent": false_write,
        "health_safety_critical_miss": critical_miss,
    }


def _project(case: dict[str, Any], decision: Any) -> dict[str, Any]:
    return {
        "id": case["id"],
        "expected": case["primary"],
        "actual": decision.primary_intent,
        "health_expected": bool(case.get("health")),
        "health_actual": bool(decision.health_context),
        "clarification_expected": bool(case.get("clarification")),
        "clarification_actual": decision.clarification_required,
        "negated_expected": case.get("negated"),
        "write_actual": decision.explicit_write_action,
    }


async def _evaluate_b(cases: list[dict[str, Any]]) -> dict[str, Any]:
    router = SemanticRouterService(mode="shadow", slm_adapter=None)
    predictions = [_project(case, (await router.parse(case["text"])).decision) for case in cases]
    return _metrics(predictions)


def _evaluate_a(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return _metrics([_project(case, classify_turn_intent(case["text"])) for case in cases])


def _source_exclusions(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Exact normalized exclusion check against development/test text assets."""

    sources = [
        ROOT / "tests" / "fixtures" / "turn_intent_development_v1.json",
        *ROOT.glob("tests/test_*.py"),
    ]
    corpus = "\n".join(
        source.read_text(encoding="utf-8") for source in sources if source.exists()
    )
    overlaps = [case["id"] for case in cases if normalize_turn_text(case["text"]) in normalize_turn_text(corpus)]
    return {"checked_sources": [str(source.relative_to(ROOT)) for source in sources if source.exists()], "exact_normalized_overlaps": overlaps}


async def _main() -> None:
    cases = _load_cases()
    if len(cases) < 120:
        raise SystemExit("Holdout must contain at least 120 cases")
    payload: dict[str, Any] = {
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "category_distribution": dict(Counter(case["primary"] for case in cases)),
        "oracle_provenance": "AUTOMATED",
        "exclusion_index": _source_exclusions(cases),
        "A_legacy": _evaluate_a(cases),
        "B_server_cascade_slm_disabled": await _evaluate_b(cases),
        "C_server_slm_enabled": (
            {"status": "NOT_RUN", "reason": "SERVER_SEMANTIC_ROUTER_MODEL_NOT_CONFIGURED"}
            if not settings.server_semantic_router_model
            else {"status": "NOT_RUN", "reason": "REAL_RUNTIME_REQUIRES_EXPLICIT_QUALIFICATION_RUN"}
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(_main())
