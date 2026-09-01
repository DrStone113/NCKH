"""Print E4.0 development metrics without opening frozen research cases."""

from __future__ import annotations

import json

from services.workout_planner.evaluator import evaluate_development_dataset


if __name__ == "__main__":
    print(json.dumps(evaluate_development_dataset(), ensure_ascii=False, indent=2))
