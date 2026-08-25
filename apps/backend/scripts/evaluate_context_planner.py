"""Print D3.0 synthetic shadow-planner metrics as JSON."""

import json

from services.agent.context_planner.evaluator import evaluate_scenarios


if __name__ == "__main__":
    print(json.dumps(evaluate_scenarios(), ensure_ascii=False, indent=2))
