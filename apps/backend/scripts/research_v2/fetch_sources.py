"""Fetch approved V2 raw sources with cache, retry, and SHA-256 provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "apps/backend/data/research_v2"
REGISTRY = DATA / "source_registry_v2.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, destination: Path, retries: int) -> tuple[str, bool]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size:
        return sha256(destination), True
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, retries + 1):
        start = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "NCKH-THS2025-78-research-v2/1.0"}
        if start:
            headers["Range"] = f"bytes={start}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                # A server that ignores Range returns 200. Restart rather than
                # concatenating a whole archive to a partial one.
                mode = "ab" if start and response.status == 206 else "wb"
                with partial.open(mode) as handle:
                    while block := response.read(1024 * 1024):
                        handle.write(block)
            partial.replace(destination)
            return sha256(destination), False
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == retries:
                raise RuntimeError(f"FETCH_FAILED:{destination.name}:{type(exc).__name__}") from exc
            time.sleep(min(2**attempt, 8))
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    source = next(item for item in registry["sources"] if item["source_id"] == "USDA_FDC_SR_LEGACY_2018")
    destination = DATA / "raw/FoodData_Central_sr_legacy_food_json_2018-04.zip"
    digest, cache_hit = fetch(str(source["download_url"]), destination, args.retries)
    source["raw_sha256"] = digest
    source["accessed_at"] = datetime.now(timezone.utc).isoformat()
    source["inclusion_status"] = "FETCHED_APPROVED"
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"source_id": source["source_id"], "path": str(destination.relative_to(ROOT)).replace("\\", "/"), "sha256": digest, "cache_hit": cache_hit, "accessed_at": source["accessed_at"]}
    (DATA / "manifests/fetch_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (DATA / "manifests/fetch_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
