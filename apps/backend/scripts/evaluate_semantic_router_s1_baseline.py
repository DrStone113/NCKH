"""Evaluate the unchanged deterministic routers on S1 DEVELOPMENT cases."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from services.agent.context_planner.classifier import classify_intent
from services.agent.scope_guard import ScopeGuard


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = (
    BACKEND_ROOT
    / "validation"
    / "semantic_router_s1"
    / "semantic_router_s1_development.jsonl"
)


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in load_cases(path):
        result = classify_intent(case["text"])
        scope = ScopeGuard().classify_fast(case["text"])
        actual_secondary = {item.value for item in result.secondary_intents}
        expected_secondary = set(case.get("expected_secondary", []))
        scope_expected = case.get("expected_scope")
        scope_actual = scope.fragments[0].scope.value if scope.fragments else None
        row = {
            "id": case["id"],
            "category": case["category"],
            "primary_correct": result.primary_intent.value
            == case["expected_primary"],
            "secondary_correct": expected_secondary.issubset(actual_secondary),
            "write_correct": result.explicit_write == case["expected_write"],
            "scope_correct": scope_expected is None or scope_actual == scope_expected,
            "actual_primary": result.primary_intent.value,
            "actual_secondary": sorted(actual_secondary),
            "actual_write": result.explicit_write,
            "actual_action_kind": result.action_kind,
            "actual_scope": scope_actual,
        }
        rows.append(row)
        groups[case["category"]].append(row)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        return {
            "count": count,
            "primary_correct": sum(item["primary_correct"] for item in items),
            "primary_accuracy": round(
                sum(item["primary_correct"] for item in items) / count, 4
            ),
            "secondary_correct": sum(item["secondary_correct"] for item in items),
            "write_correct": sum(item["write_correct"] for item in items),
            "scope_correct": sum(item["scope_correct"] for item in items),
        }

    false_positive_write = sum(
        not case["expected_write"] and row["actual_write"]
        for case, row in zip(load_cases(path), rows, strict=True)
    )
    return {
        "artifact_type": "SYNTHETIC_DEVELOPMENT",
        "router": "context-intent-v1 deterministic baseline",
        "dataset": path.name,
        "overall": summarize(rows),
        "by_category": {
            category: summarize(items) for category, items in sorted(groups.items())
        },
        "hard_failures": {"false_positive_write_intent": false_positive_write},
        "failures": [row for row in rows if not all(
            (row["primary_correct"], row["secondary_correct"], row["write_correct"], row["scope_correct"])
        )],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.dataset)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
