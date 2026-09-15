"""Report Plan V2 qualification with historical V1 and current scopes separate.

This is an audit-only companion to the original fail-closed verifier. It does
not edit a historical contaminated dataset, run acceptance, score a candidate,
or change any P2 frozen source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:  # ``python -m scripts...``
    from scripts.verify_plan_v2_qualification import _flutter_versions
except ModuleNotFoundError:  # direct script execution from the backend root
    from verify_plan_v2_qualification import _flutter_versions


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"


def _load(name: str) -> dict[str, Any]:
    return json.loads((VALIDATION / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _default_flutter() -> str | None:
    candidate = ROOT.parent / "mobile" / ".fvm" / "flutter_sdk" / "bin" / "flutter.bat"
    return str(candidate) if candidate.is_file() else None


def evaluate_scoped(flutter_executable: str | None = None) -> dict[str, Any]:
    """Return a non-scoring, scope-aware status for the P2.1A automated freeze."""

    historical = _load("acceptance-v1-qualification-status.json")
    automated = _load("p2-1a-automated-freeze-manifest-v1.json")
    execution = flutter_executable or _default_flutter()
    flutter_version, dart_version, flutter_error = _flutter_versions(execution)
    artifact_hashes = {
        name: {
            "expected": entry["sha256"],
            "actual": _sha(VALIDATION / entry["path"]),
            "matches": _sha(VALIDATION / entry["path"]) == entry["sha256"],
        }
        for name, entry in automated["artifacts"].items()
    }
    implementation_manifest = _load("implementation-freeze-p2-1r-v1.json")
    source_mismatches = {
        path: {"expected": expected, "actual": _sha(ROOT / path)}
        for path, expected in implementation_manifest["sources"].items()
        if _sha(ROOT / path) != expected
    }
    preflight = automated.get("final_preflight") or {}
    current_ready = (
        automated.get("status") == "FROZEN"
        and automated.get("review_mode") == "AUTOMATED"
        and automated.get("READY_TO_RUN_P2_1_ACCEPTANCE") is True
        and all(item["matches"] for item in artifact_hashes.values())
        and not source_mismatches
        and flutter_version == "3.44.8"
        and dart_version == "3.12.2"
        and all(bool(value) for value in preflight.values())
    )
    return {
        "HISTORICAL_V1_CONTAMINATED": (
            historical.get("status") == "CONTAMINATED"
            and historical.get("dataset_role") == "CONTAMINATED_DEVELOPMENT"
            and historical.get("acceptance_eligible") is False
        ),
        "CURRENT_ACCEPTANCE_QUALIFICATION_STATUS": (
            "READY_FOR_FIRST_SCORED_ACCEPTANCE"
            if current_ready
            else "NOT_READY_FOR_FIRST_SCORED_ACCEPTANCE"
        ),
        "CURRENT_ACCEPTANCE_QUALIFICATION_READY": current_ready,
        "CURRENT_SCOPE": "P2_1A_AUTOMATED_FREEZE",
        "diagnostics": {
            "historical_v1_status": historical.get("status"),
            "historical_v1_role": historical.get("dataset_role"),
            "historical_v1_rewritten": False,
            "automated_freeze_status": automated.get("status"),
            "automated_review_mode": automated.get("review_mode"),
            "automated_freeze_ready_claim": automated.get("READY_TO_RUN_P2_1_ACCEPTANCE"),
            "artifact_hashes": artifact_hashes,
            "source_mismatches": source_mismatches,
            "flutter_executable": execution,
            "flutter_version": flutter_version,
            "dart_version": dart_version,
            "flutter_error": flutter_error,
            "release_qualification_claimed": False,
            "scored_acceptance_executed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flutter", help="Pinned Flutter executable; defaults to the project-local P2.1R SDK.")
    parser.add_argument("--require-current-ready", action="store_true")
    args = parser.parse_args()
    result = evaluate_scoped(args.flutter)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not args.require_current_ready or result["CURRENT_ACCEPTANCE_QUALIFICATION_READY"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
