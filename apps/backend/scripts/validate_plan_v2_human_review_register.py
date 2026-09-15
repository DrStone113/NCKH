"""Validate a P2.1H human review register without running Plan V2.

It supports one or more human reviews per case and explicit adjudication.  The
``--require-freeze-ready`` mode is deliberately fail-closed and is not used to
freeze anything by itself.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ALLOWED = {
    "ACCEPT", "REVISE_BEFORE_FREEZE", "REJECT_AMBIGUOUS", "REJECT_DUPLICATE",
    "REJECT_LEAKAGE", "REJECT_OUT_OF_SCOPE",
}
PENDING = "PENDING_HUMAN_REVIEW"


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _complete(review: dict[str, Any]) -> bool:
    return (
        review.get("decision") in ALLOWED
        and isinstance(review.get("reviewer_id"), str) and bool(review["reviewer_id"].strip())
        and _valid_timestamp(review.get("reviewed_at"))
        and isinstance(review.get("reason"), str) and bool(review["reason"].strip())
    )


def validate(register: dict[str, Any], expected_case_ids: set[str]) -> dict[str, Any]:
    records = register.get("review_records", [])
    ids = [record.get("case_id") for record in records]
    missing = sorted(expected_case_ids - set(ids))
    unexpected = sorted(set(ids) - expected_case_ids)
    duplicate_ids = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    completed: dict[str, list[dict[str, Any]]] = {}
    disagreements: list[str] = []
    adjudication_errors: list[str] = []
    pair_labels: list[tuple[str, str]] = []
    for record in records:
        case_id = str(record.get("case_id"))
        reviews = record.get("reviews", [])
        complete_reviews = [review for review in reviews if _complete(review)]
        if complete_reviews:
            completed[case_id] = complete_reviews
        if len(complete_reviews) >= 2:
            first, second = str(complete_reviews[0]["decision"]), str(complete_reviews[1]["decision"])
            pair_labels.append((first, second))
            if first != second:
                disagreements.append(case_id)
        adjudication = record.get("adjudication", {})
        final = adjudication.get("final_decision", PENDING)
        if final != PENDING:
            if final not in ALLOWED or not isinstance(adjudication.get("adjudicator_id"), str) or not adjudication["adjudicator_id"].strip() or not _valid_timestamp(adjudication.get("adjudicated_at")) or not isinstance(adjudication.get("reason"), str) or not adjudication["reason"].strip():
                adjudication_errors.append(case_id)
            elif case_id in disagreements and final not in {review["decision"] for review in complete_reviews}:
                adjudication_errors.append(case_id)
    agreement = None
    kappa = None
    if pair_labels:
        agreement = sum(left == right for left, right in pair_labels) / len(pair_labels)
        left_counts = Counter(left for left, _ in pair_labels)
        right_counts = Counter(right for _, right in pair_labels)
        expected = sum((left_counts[label] / len(pair_labels)) * (right_counts[label] / len(pair_labels)) for label in ALLOWED)
        kappa = None if expected == 1 else (agreement - expected) / (1 - expected)
    all_cases_reviewed = len(completed) == len(expected_case_ids) and not missing and not unexpected and not duplicate_ids
    all_adjudicated = all(
        record.get("adjudication", {}).get("final_decision", PENDING) in ALLOWED
        for record in records
    ) and not adjudication_errors
    return {
        "case_count_expected": len(expected_case_ids),
        "case_count_in_register": len(records),
        "human_review_coverage_percent": round(100 * len(completed) / len(expected_case_ids), 2) if expected_case_ids else 0.0,
        "missing_case_ids": missing,
        "unexpected_case_ids": unexpected,
        "duplicate_case_ids": duplicate_ids,
        "reviewer_disagreement_case_ids": disagreements,
        "reviewer_pair_count": len(pair_labels),
        "percent_agreement": None if agreement is None else round(100 * agreement, 2),
        "cohens_kappa": None if kappa is None else round(kappa, 4),
        "adjudication_errors": adjudication_errors,
        "all_cases_reviewed": all_cases_reviewed,
        "all_cases_adjudicated": all_adjudicated,
        "freeze_ready": all_cases_reviewed and all_adjudicated and not disagreements,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("register", type=Path)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--require-freeze-ready", action="store_true")
    args = parser.parse_args()
    register = json.loads(args.register.read_text(encoding="utf-8"))
    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    result = validate(register, {case["case_id"] for case in pack["cases"]})
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not args.require_freeze_ready or result["freeze_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
