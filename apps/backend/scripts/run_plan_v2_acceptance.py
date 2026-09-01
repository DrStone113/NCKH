"""Fail-closed entry point reserved for a future scored Plan V2 acceptance run.

P2.1R deliberately contains no scoring implementation.  The non-bypassable
preflight is invoked first so a later runner cannot score an unqualified set.
"""

from __future__ import annotations

import argparse
from scripts.verify_plan_v2_qualification import evaluate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flutter", required=True, help="Pinned Flutter executable, never global PATH.")
    args = parser.parse_args()
    result = evaluate(args.flutter)
    if not result["READY_TO_RUN_P2_1_ACCEPTANCE"]:
        print("PLAN_V2_ACCEPTANCE_BLOCKED: qualification preflight is not green")
        return 2
    print("PLAN_V2_ACCEPTANCE_SCORING_NOT_IMPLEMENTED: P2.1R ends before first scored execution")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
