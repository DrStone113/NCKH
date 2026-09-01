"""Build the Plan V2 development/evaluation exclusion index.

The index is a protocol artefact: it does not call Plan V2 and must be run
before a candidate holdout is reviewed or frozen.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
REPO = ROOT.parents[1]


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", without_marks).split())


def _record(*, stable_id: str, source: str, use: str, text: str | None, location: str | None = None) -> dict[str, Any]:
    return {
        "stable_id": stable_id,
        "source": source,
        "classification": "USED_FOR_DEVELOPMENT",
        "use": use,
        "text": text,
        "normalized_text": normalize_text(text) if text else None,
        "location": location,
    }


def _fixture_literals(path: Path) -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(REPO).as_posix()
    records: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value.strip()) >= 8:
            text = node.value.strip()
            digest = hashlib.sha256(f"{relative}:{node.lineno}:{text}".encode()).hexdigest()[:16]
            records.append(
                _record(
                    stable_id=f"REGRESSION_LITERAL:{digest}",
                    source=relative,
                    use="REGRESSION_FIXTURE_LITERAL",
                    text=text,
                    location=f"{relative}:{node.lineno}",
                )
            )
    return records


def build_index() -> dict[str, Any]:
    p1 = json.loads((VALIDATION / "p1-development-v2-inventory.json").read_text(encoding="utf-8"))
    natural = json.loads((VALIDATION / "natural-development-v1.json").read_text(encoding="utf-8"))
    contaminated = json.loads((VALIDATION / "acceptance-v1.json").read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for scenario_id in p1["scenario_ids"]:
        records.append(
            _record(
                stable_id=scenario_id,
                source=p1["source_path"],
                use="P1_DEVELOPMENT_SCENARIO",
                text=None,
            )
        )
    for prompt in natural["prompts"]:
        records.append(
            _record(
                stable_id=prompt["prompt_id"],
                source="natural-development-v1.json",
                use="P2_NATURAL_DEVELOPMENT",
                text=prompt["prompt"],
            )
        )
    for case in contaminated["cases"]:
        records.append(
            _record(
                stable_id=case["case_id"],
                source="acceptance-v1.json",
                use="P2_CONTAMINATED_ACCEPTANCE",
                text=case["prompt"],
            )
        )
    for test_name in (
        "test_plan_engine_p1.py",
        "test_plan_engine_p2.py",
        "test_plan_tools.py",
        "test_plan_sql_repository_live.py",
    ):
        records.extend(_fixture_literals(ROOT / "tests" / test_name))
    records.sort(key=lambda record: record["stable_id"])
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "index_version": "PLAN_V2_DEVELOPMENT_EXCLUSION_INDEX_V1",
        "purpose": "Leakage prevention only; it is not a benchmark or Plan V2 input.",
        "normalization": "NFKD/no-combining-marks/casefold/non-alphanumeric-collapse",
        "record_count": len(records),
        "text_record_count": sum(record["text"] is not None for record in records),
        "canonical_records_sha256": hashlib.sha256(canonical).hexdigest(),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=VALIDATION / "development-exclusion-index-v1.json")
    args = parser.parse_args()
    payload = build_index()
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("index_version", "record_count", "text_record_count", "canonical_records_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
