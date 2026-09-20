"""Evaluate rule, small-model, LLM-judge, or hybrid scope routing.

Input is JSONL with: id, text, expected_intent, expected_scope and
evidence_class.  Use SYNTHETIC_DEVELOPMENT for fixtures and a distinct
HUMAN_LABELLED_HOLDOUT dataset for final research claims; this script never
silently relabels one as the other.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from services.agent.llm_client import LLMClient
from services.agent.scope_evaluation import (
    ScopeEvaluationRecord,
    summarize_scope_evaluation,
)
from services.agent.scope_guard import (
    ScopeCategory,
    ScopeGuard,
    ScopeIntent,
    StrictJSONScopeClassifier,
    intent_for_scope,
)
from services.agent.semantic_scope_classifier import SemanticPrototypeScopeClassifier


_EVIDENCE_CLASSES = frozenset({"SYNTHETIC_DEVELOPMENT", "HUMAN_LABELLED_HOLDOUT"})


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument(
        "--mode",
        choices=("rule-only", "small-only", "llm-only", "hybrid"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--judge-cost-usd", type=float, default=0.0)
    return parser.parse_args()


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        required = {"id", "text", "expected_intent", "expected_scope", "evidence_class"}
        if not isinstance(row, dict) or not required.issubset(row):
            raise ValueError(f"invalid dataset row {line_number}")
        if row["evidence_class"] not in _EVIDENCE_CLASSES:
            raise ValueError(f"invalid evidence_class at row {line_number}")
        ScopeIntent(row["expected_intent"])
        ScopeCategory(row["expected_scope"])
        rows.append(row)
    if not rows:
        raise ValueError("dataset is empty")
    return rows


def _small_classifier() -> SemanticPrototypeScopeClassifier:
    if not settings.scope_router_model:
        raise RuntimeError("SCOPE_ROUTER_MODEL is required for this mode")
    return SemanticPrototypeScopeClassifier(
        settings.scope_router_model,
        device=settings.scope_router_device,
        temperature=settings.scope_router_temperature,
        full_confidence_similarity=settings.scope_router_full_confidence_similarity,
    )


def _judge() -> StrictJSONScopeClassifier:
    if not settings.scope_classifier_model or not settings.openai_api_key:
        raise RuntimeError("SCOPE_CLASSIFIER_MODEL and OPENAI_API_KEY are required for this mode")
    llm = LLMClient(
        model=settings.scope_classifier_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        request_timeout_s=settings.scope_classifier_timeout_seconds,
        allow_model_fallback=False,
        reasoning_effort=settings.llm_reasoning_effort,
    )
    return StrictJSONScopeClassifier(
        llm,
        model_version=settings.scope_classifier_model,
        timeout_seconds=settings.scope_classifier_timeout_seconds,
    )


async def _evaluate(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    small = _small_classifier() if mode in {"small-only", "hybrid"} else None
    judge = _judge() if mode in {"llm-only", "hybrid"} else None
    guard = ScopeGuard(
        judge,
        classifier_threshold=settings.scope_classifier_confidence,
        primary_classifier=small if mode == "hybrid" else None,
        primary_low_confidence=settings.scope_router_low_confidence,
        primary_high_confidence=settings.scope_router_high_confidence,
        primary_timeout_seconds=settings.scope_router_timeout_seconds,
    )
    records: list[ScopeEvaluationRecord] = []
    predictions: list[dict[str, Any]] = []

    for row in rows:
        started = time.perf_counter()
        if mode == "rule-only":
            decision = guard.classify_fast(row["text"])
            scope = decision.category
            intent = decision.intent
            judge_calls = 0
            method = decision.method
        elif mode == "small-only":
            prediction = await small.classify(row["text"])
            scope = prediction.scope
            intent = prediction.intent or intent_for_scope(scope, prediction.reason_code)
            judge_calls = 0
            method = f"SMALL_INTENT_CLASSIFIER:{prediction.model_version}"
        elif mode == "llm-only":
            prediction = await judge.classify(row["text"])
            scope = prediction.scope
            intent = prediction.intent or intent_for_scope(scope, prediction.reason_code)
            judge_calls = 1
            method = f"LLM_SCOPE_JUDGE:{prediction.model_version}"
        else:
            decision = await guard.classify(row["text"])
            scope = decision.category
            intent = decision.intent
            judge_calls = sum(
                fragment.method.startswith("LLM_SCOPE_JUDGE:")
                or fragment.method.startswith("LLM_SCOPE_JUDGE_FALLBACK:")
                for fragment in decision.fragments
            )
            method = decision.method
        latency_ms = (time.perf_counter() - started) * 1000.0
        records.append(
            ScopeEvaluationRecord(
                ScopeCategory(row["expected_scope"]),
                scope,
                ScopeIntent(row["expected_intent"]),
                intent,
                latency_ms,
                judge_calls,
            )
        )
        predictions.append(
            {
                "id": row["id"],
                "evidence_class": row["evidence_class"],
                "predicted_intent": intent.value,
                "predicted_scope": scope.value,
                "method": method,
                "latency_ms": latency_ms,
                "judge_calls": judge_calls,
            }
        )

    return {
        "schema_version": "scope-router-v2-evaluation-v1",
        "mode": mode,
        "evidence_classes": sorted({row["evidence_class"] for row in rows}),
        "metrics": summarize_scope_evaluation(records),
        "predictions": predictions,
    }


def main() -> None:
    args = _arguments()
    rows = _load_dataset(args.dataset)
    report = asyncio.run(_evaluate(rows, args.mode))
    report["metrics"]["estimated_judge_cost_usd"] = (
        report["metrics"]["judge_calls"] * max(0.0, args.judge_cost_usd)
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
