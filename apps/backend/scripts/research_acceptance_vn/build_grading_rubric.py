"""Freeze the answer-quality rubric before any acceptance generation call."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / "evaluation" / "acceptance_vn" / "grading_rubric_v1.json"

PROMPT = """You are a strict evaluation judge for a Vietnamese health/nutrition chatbot.
Score only the supplied answer against the supplied expected channel, structured tool result,
and retrieved evidence. Do not supply medical advice or improve the answer. Return one JSON
object with relevance (0 or 1), faithfulness (0 or 1), unsupported_claim (true or false),
provenance_correct (0 or 1), and a short reason. A tool-owned answer is faithful when every
material factual value is present in the structured tool result. A RAG-owned answer is
faithful when every material claim is supported by a supplied chunk/source. NO_EVIDENCE is
correct only when it does not invent an unavailable fact, diagnosis, or dose."""


def main() -> int:
    payload = {
        "schema_version": "acceptance-answer-rubric-v1",
        "judge_mode": "SEMANTIC_JUDGE_ONLY_FOR_NONDETERMINISTIC_DIMENSIONS",
        "deterministic_checks": [
            "channel and tool correctness",
            "tool-backed numeric/identity values",
            "RAG source IDs",
            "NO_EVIDENCE handling",
            "write/readback identity",
        ],
        "semantic_dimensions": ["answer_relevance", "faithfulness", "unsupported_claim", "provenance_correctness"],
        "prompt": PROMPT,
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "judge_provider": "UNSET_BEFORE_RUN",
        "judge_model": "UNSET_BEFORE_RUN",
        "judge_model_independent": "UNSET_BEFORE_RUN",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != encoded:
        raise RuntimeError("GRADING_RUBRIC_ALREADY_FROZEN")
    OUTPUT.write_text(encoded, encoding="utf-8")
    print(json.dumps({"path": str(OUTPUT.relative_to(ROOT)), "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
