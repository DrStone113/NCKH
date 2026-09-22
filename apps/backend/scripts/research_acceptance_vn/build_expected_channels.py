"""Freeze the architecture-derived channel projection for acceptance-vn.

This script never alters the frozen case file or its retrieval oracle.  The
mapping is deliberately keyed only by the frozen case domain and the
version-controlled Context Planner/tool policy; it must not be changed from
observed retrieval or generation outcomes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
CASES = ROOT / "evaluation" / "acceptance_vn" / "cases.jsonl"
OUTPUT = ROOT / "evaluation" / "acceptance_vn" / "expected_channels.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# The source map is intentionally static: it encodes the production policy
# matrix, not a post-hoc preference for whatever evaluated best.
_BY_DOMAIN: dict[str, dict[str, Any]] = {
    "VN_FOOD": {
        "expected_channel": "FOOD_TOOL",
        "expected_tool_names": ["search_food_nutrition"],
        "rag_required": False,
        "rag_forbidden": True,
        "evidence_requirement": "STRUCTURED_TOOL_DATA",
        "derivation_source": [
            "context-source-matrix-v1:FOOD_NUTRITION_LOOKUP",
            "services/agent/context_planner/matrix.py:FOOD_DATABASE required; RAG forbidden",
        ],
    },
    "FOREIGN_FOOD": {
        "expected_channel": "FOOD_TOOL",
        "expected_tool_names": ["search_food_nutrition"],
        "rag_required": False,
        "rag_forbidden": True,
        "evidence_requirement": "STRUCTURED_TOOL_DATA",
        "derivation_source": [
            "context-source-matrix-v1:FOOD_NUTRITION_LOOKUP",
            "services/agent/context_planner/matrix.py:FOOD_DATABASE required; RAG forbidden",
        ],
    },
    "VN_DISH": {
        "expected_channel": "DISH_TOOL",
        "expected_tool_names": ["search_dish_catalog"],
        "rag_required": False,
        "rag_forbidden": True,
        "evidence_requirement": "STRUCTURED_TOOL_DATA",
        "derivation_source": [
            "context-source-matrix-v1:MEAL_RECOMMENDATION",
            "services/agent/context_planner/matrix.py:DISH_DATABASE required; RAG forbidden",
            "services/agent/system_prompt.py:explicit dish names query search_dish_catalog first",
        ],
    },
    "EXERCISE_CATALOG": {
        "expected_channel": "EXERCISE_TOOL",
        "expected_tool_names": ["search_exercise_catalog"],
        "rag_required": False,
        "rag_forbidden": True,
        "evidence_requirement": "STRUCTURED_TOOL_DATA",
        "derivation_source": [
            "context-source-matrix-v1:WORKOUT_RECOMMENDATION",
            "services/agent/context_planner/matrix.py:exercise recommendation forbids RAG",
            "services/agent/tools/workout.py:search_exercise_catalog",
        ],
    },
    "VN_BODY_METRIC": {
        "expected_channel": "RAG_KNOWLEDGE",
        "expected_tool_names": ["query_rag"],
        "rag_required": True,
        "rag_forbidden": False,
        "evidence_requirement": "GROUNDED_EVIDENCE",
        "derivation_source": [
            "context-source-matrix-v1:GENERAL_NUTRITION_KNOWLEDGE",
            "services/agent/context_planner/matrix.py:RAG required for non-personal knowledge",
        ],
    },
    "VN_NUTRITION_GUIDELINE": {
        "expected_channel": "RAG_KNOWLEDGE",
        "expected_tool_names": ["query_rag"],
        "rag_required": True,
        "rag_forbidden": False,
        "evidence_requirement": "GROUNDED_EVIDENCE",
        "derivation_source": [
            "context-source-matrix-v1:GENERAL_NUTRITION_KNOWLEDGE",
            "services/agent/context_planner/matrix.py:RAG required; evidence grounding",
        ],
    },
    "VN_NUTRIENT_REQUIREMENT": {
        "expected_channel": "RAG_KNOWLEDGE",
        "expected_tool_names": ["query_rag"],
        "rag_required": True,
        "rag_forbidden": False,
        "evidence_requirement": "GROUNDED_EVIDENCE",
        "derivation_source": [
            "context-source-matrix-v1:GENERAL_NUTRITION_KNOWLEDGE",
            "services/agent/context_planner/matrix.py:RAG required; evidence grounding",
        ],
    },
    "VN_MICRONUTRIENT": {
        "expected_channel": "RAG_KNOWLEDGE",
        "expected_tool_names": ["query_rag"],
        "rag_required": True,
        "rag_forbidden": False,
        "evidence_requirement": "GROUNDED_EVIDENCE",
        "derivation_source": [
            "context-source-matrix-v1:GENERAL_NUTRITION_KNOWLEDGE",
            "services/agent/context_planner/matrix.py:RAG required; evidence grounding",
        ],
    },
    "VN_PHYSICAL_ACTIVITY": {
        "expected_channel": "RAG_KNOWLEDGE",
        "expected_tool_names": ["query_rag"],
        "rag_required": True,
        "rag_forbidden": False,
        "evidence_requirement": "GROUNDED_EVIDENCE",
        "derivation_source": [
            "context-source-matrix-v1:GENERAL_NUTRITION_KNOWLEDGE",
            "services/agent/context_planner/matrix.py:RAG required for general guidance",
        ],
    },
    "GLOBAL_HEALTH": {
        "expected_channel": "RAG_KNOWLEDGE",
        "expected_tool_names": ["query_rag"],
        "rag_required": True,
        "rag_forbidden": False,
        "evidence_requirement": "GROUNDED_EVIDENCE",
        "derivation_source": [
            "context-source-matrix-v1:GENERAL_NUTRITION_KNOWLEDGE",
            "services/agent/context_planner/matrix.py:RAG required; medical-evidence tool reserved for explicit evidence requests",
        ],
    },
    "NO_EVIDENCE": {
        "expected_channel": "NO_EVIDENCE",
        "expected_tool_names": [],
        "rag_required": False,
        "rag_forbidden": True,
        "evidence_requirement": "SAFETY_LIMITATION",
        "derivation_source": [
            "services/agent/scope_guard.py:out-of-scope and unsafe requests are deterministically bounded",
            "services/agent/context_planner/matrix.py:SMALLTALK_OR_OTHER forbids RAG and MEDICAL_EVIDENCE",
        ],
    },
}


def main() -> int:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]
    projection: list[dict[str, Any]] = []
    for case in cases:
        domain = str(case["domain"])
        try:
            policy = _BY_DOMAIN[domain]
        except KeyError as exc:
            raise RuntimeError(f"UNMAPPED_ACCEPTANCE_DOMAIN:{domain}") from exc
        projection.append({"case_id": case["case_id"], **policy})
    if len(projection) != len(cases) or len({item["case_id"] for item in projection}) != len(cases):
        raise RuntimeError("INVALID_CHANNEL_PROJECTION")
    payload = {
        "schema_version": "acceptance-expected-channels-v1",
        "case_file": "evaluation/acceptance_vn/cases.jsonl",
        "case_file_sha256": _sha256(CASES),
        "case_count": len(projection),
        "projection": projection,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != encoded:
        raise RuntimeError("EXPECTED_CHANNEL_PROJECTION_ALREADY_FROZEN")
    OUTPUT.write_text(encoded, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "sha256": _sha256(OUTPUT), "case_count": len(projection)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
