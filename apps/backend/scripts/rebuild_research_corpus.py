"""Atomically rebuild the dedicated frozen research corpus."""

from __future__ import annotations

import asyncio
import json

from services.experiment.corpus import rebuild_research_corpus
from services.experiment.errors import ExperimentError


async def _run() -> int:
    try:
        manifest = await rebuild_research_corpus()
    except ExperimentError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {"ok": True, "manifest": manifest.model_dump(mode="json")},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
