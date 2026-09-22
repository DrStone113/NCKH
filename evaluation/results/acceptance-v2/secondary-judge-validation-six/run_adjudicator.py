"""Blind third-model check for only the six secondary/primary disagreement cases."""
from __future__ import annotations

import json
import time
from pathlib import Path

from openai import OpenAI

import run_secondary as source

source.MODEL = "cnb/grok-4.5"
source.PROVIDER = "cnb via api.vilao.ai"
OUTPUT = Path(__file__).resolve().parent / "adjudicator_grok_judgments.jsonl"


def main() -> None:
    prior = [json.loads(line) for line in OUTPUT.read_text(encoding="utf-8").splitlines()] if OUTPUT.exists() else []
    if [row["case_id"] for row in prior] != list(source.RUNS)[:len(prior)]:
        raise RuntimeError("INVALID_ADJUDICATOR_CHECKPOINT")
    remaining = list(source.RUNS)[len(prior):]
    client = OpenAI(base_url=source.settings.openai_base_url, api_key=source.settings.openai_api_key or "dummy-key", max_retries=0, timeout=90)
    with OUTPUT.open("a", encoding="utf-8") as handle:
        for case_id in remaining:
            judged = source.grade(client, case_id)
            handle.write(json.dumps(judged, ensure_ascii=False) + "\n")
            handle.flush()
            print(json.dumps({"case_id": case_id, "grade": judged["grade"]}, ensure_ascii=True), flush=True)
            if case_id != remaining[-1]:
                time.sleep(15)


if __name__ == "__main__":
    main()
