"""Fetch cacheable, legally reviewed raw inputs for the final research corpus.

The script never downloads Vietnamese NIN prose because this repository has no
verified redistribution permission for it.  It records a hash and retrieval
time for every downloaded input so normalization is reproducible offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from urllib.error import HTTPError
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "apps/backend/data/research_final"
REGISTRY = DATA / "source_registry.json"
RAW = DATA / "raw"

DOWNLOADS = {
    "USDA_FDC_FOUNDATION_2026": (
        "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_json_2026-04-30.zip",
        RAW / "usda_foundation_2026.zip",
    ),
    "MEDLINEPLUS_HEALTH_TOPICS": (
        "https://medlineplus.gov/xml/mplus_topics_compressed_2026-09-19.zip",
        RAW / "medlineplus_topics.zip",
    ),
}
DEFINITION_DOWNLOADS = {
    "vitamins": "https://medlineplus.gov/xml/vitaminsdefinitions.xml",
    "minerals": "https://medlineplus.gov/xml/mineralsdefinitions.xml",
    "nutrition": "https://medlineplus.gov/xml/nutritiondefinitions.xml",
    "fitness": "https://medlineplus.gov/xml/fitnessdefinitions.xml",
}
ODS_SLUGS = (
    "VitaminA", "Thiamin", "Riboflavin", "Niacin", "PantothenicAcid", "VitaminB6",
    "Biotin", "Folate", "VitaminB12", "VitaminC", "VitaminD", "VitaminE", "VitaminK",
    "Calcium", "Iron", "Magnesium", "Zinc", "Iodine", "Selenium", "Copper", "Potassium",
    "Choline", "Omega3FattyAcids",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, path: Path, *, refresh: bool) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        return sha256(path)
    failure: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NCKH-research-final/1.0 (+source registry)"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
            if len(payload) < 100:
                raise RuntimeError(f"SHORT_DOWNLOAD:{url}")
            path.write_bytes(payload)
            return sha256(path)
        except Exception as exc:  # retry transport failures only
            failure = exc
            if isinstance(exc, HTTPError) and 400 <= exc.code < 500:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"DOWNLOAD_FAILED:{url}:{failure}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    registry: dict[str, Any] = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {item["source_id"]: item for item in registry["sources"]}
    downloaded: dict[str, str] = {}
    for source_id, (url, path) in DOWNLOADS.items():
        digest = fetch(url, path, refresh=args.refresh)
        by_id[source_id]["raw_sha256"] = digest
        downloaded[source_id] = digest
    definition_hashes: dict[str, str] = {}
    for name, url in DEFINITION_DOWNLOADS.items():
        definition_hashes[name] = fetch(url, RAW / "medlineplus_definitions" / f"{name}.xml", refresh=args.refresh)
    by_id["MEDLINEPLUS_DEFINITIONS"]["raw_sha256"] = hashlib.sha256(
        json.dumps(definition_hashes, sort_keys=True).encode("utf-8")
    ).hexdigest()
    ods_hashes: dict[str, str] = {}
    ods_failures: dict[str, str] = {}
    for slug in ODS_SLUGS:
        url = f"https://ods.od.nih.gov/factsheets/{slug}-Consumer/"
        try:
            ods_hashes[slug] = fetch(url, RAW / "ods" / f"{slug}.html", refresh=args.refresh)
        except RuntimeError as exc:
            ods_failures[slug] = str(exc)
    by_id["NIH_ODS_FACT_SHEETS"]["raw_sha256"] = hashlib.sha256(
        json.dumps(ods_hashes, sort_keys=True).encode("utf-8")
    ).hexdigest()
    registry["last_fetch_at"] = datetime.now(timezone.utc).isoformat()
    by_id["NIH_ODS_FACT_SHEETS"]["record_count_excluded"] = len(ods_failures)
    by_id["NIH_ODS_FACT_SHEETS"]["exclusion_reason"] = "Source host rejected automated download (HTTP 403); no ODS fact-sheet prose was ingested." if ods_failures else None
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "downloaded": downloaded, "definition_count": len(definition_hashes), "ods_count": len(ods_hashes), "ods_failures": ods_failures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
