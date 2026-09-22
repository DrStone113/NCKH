from __future__ import annotations

import json
from pathlib import Path

from services.agent.turn_intent import normalize_turn_text


FIXTURE = Path(__file__).with_name("fixtures") / "server_semantic_routing_holdout_v1.json"


def test_fresh_holdout_is_large_unique_and_excluded_from_development_literals():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(cases) >= 120
    assert len({case["id"] for case in cases}) == len(cases)
    assert len({normalize_turn_text(case["text"]) for case in cases}) == len(cases)

    development = Path(__file__).with_name("fixtures") / "turn_intent_development_v1.json"
    prior = json.loads(development.read_text(encoding="utf-8"))
    prior_texts = {normalize_turn_text(case["text"]) for case in prior}
    assert not prior_texts.intersection(
        normalize_turn_text(case["text"]) for case in cases
    )
