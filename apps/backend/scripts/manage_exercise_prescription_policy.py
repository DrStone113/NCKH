"""Write or verify the frozen E3 exercise-prescription policy.

Examples:
    py -3.10 scripts/manage_exercise_prescription_policy.py --write-policy
    py -3.10 scripts/manage_exercise_prescription_policy.py --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from modules.wger.exercise_prescription_policy import (  # noqa: E402
    POLICY_FILE,
    ExercisePrescriptionPolicyError,
    build_policy,
    verify_policy,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-policy", action="store_true")
    action.add_argument("--verify", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.write_policy:
            policy = build_policy()
            POLICY_FILE.write_text(
                json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result = {
                "ok": True,
                "action": "policy_written",
                "policy_version": policy["schema_version"],
                "goals": len(policy["training_goals"]),
                "evidence_sources": len(policy["evidence_registry"]),
                "content_sha256": policy["content_sha256"],
                "manifest_sha256": policy["manifest_sha256"],
            }
        else:
            result = verify_policy()
            result["action"] = "policy_verified"
    except (ExercisePrescriptionPolicyError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
