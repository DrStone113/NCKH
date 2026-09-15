"""Fit lexical early-exit thresholds from an offline labelled ranking JSONL.

Input rows contain ``query``, ``relevant_ids``, ``lexical`` and ``dense``;
rankings are lists of ``{"id": ..., "score": ...}``. The script never reads
chat tables and never writes production configuration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _ids(items, limit=5):
    return [str(item["id"]) for item in items[:limit]]


def _recall(found, relevant):
    wanted = {str(item) for item in relevant}
    return len(set(found) & wanted) / len(wanted) if wanted else 1.0


def evaluate(rows, threshold: float, margin: float):
    recalls = []
    dense_calls = 0
    for row in rows:
        lexical = row.get("lexical") or []
        first = float(lexical[0].get("score", 0)) if lexical else 0.0
        second = float(lexical[1].get("score", 0)) if len(lexical) > 1 else 0.0
        early = first >= threshold and (second <= 0 or first / second >= margin)
        ranking = lexical if early else (row.get("hybrid") or row.get("dense") or lexical)
        dense_calls += int(not early)
        recalls.append(_recall(_ids(ranking), row.get("relevant_ids") or []))
    count = max(1, len(rows))
    return sum(recalls) / count, dense_calls / count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dense-budget", type=float, default=0.40)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = []
    for threshold in (0.08, 0.12, 0.18, 0.24, 0.30, 0.40):
        for margin in (1.1, 1.25, 1.5, 1.75, 2.0):
            recall, dense_rate = evaluate(rows, threshold, margin)
            if dense_rate <= args.dense_budget:
                candidates.append((recall, -dense_rate, threshold, margin))
    if not candidates:
        raise SystemExit("NO_POLICY_WITHIN_DENSE_BUDGET")
    recall, negative_dense, threshold, margin = max(candidates)
    payload = {
        "artifact_version": "retrieval-policy-v2-grid-v1",
        "status": "OFFLINE_EVALUATED_REQUIRES_HUMAN_APPROVAL",
        "dataset_rows": len(rows),
        "lexical_confidence_threshold": threshold,
        "lexical_margin_ratio": margin,
        "recall_at_5": round(recall, 6),
        "dense_call_rate": round(-negative_dense, 6),
        "dense_budget": args.dense_budget,
        "automatic_promotion": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
