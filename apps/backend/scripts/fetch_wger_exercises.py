"""
Script cào dữ liệu bài tập từ wger.de API và lưu thành JSON.

Chạy: python scripts/fetch_wger_exercises.py
Output đồng bộ:
- backend/data/wger_exercises_raw.json
- mobile/assets/data/wger_exercises_raw.json
"""

import json
import time
from pathlib import Path

import httpx

BACKEND_OUTPUT_PATH = Path(__file__).parent.parent / "data" / "wger_exercises_raw.json"
MOBILE_OUTPUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "mobile"
    / "assets"
    / "data"
    / "wger_exercises_raw.json"
)
OUTPUT_PATHS = (BACKEND_OUTPUT_PATH, MOBILE_OUTPUT_PATH)
BASE_URL = "https://wger.de/api/v2"

# Chỉ lấy bài tập tiếng Anh (language=2)
ENDPOINT = f"{BASE_URL}/exerciseinfo/?format=json&language=2&limit=100"

TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=5.0)
HEADERS = {"User-Agent": "HealthApp/1.0"}


def fetch_all_exercises() -> list[dict]:
    results = []
    url = ENDPOINT
    page = 0
    seen_urls: set[str] = set()

    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        while url:
            if url in seen_urls:
                raise RuntimeError(f"wger pagination cycle detected: {url}")
            seen_urls.add(url)
            page += 1
            print(f"  Fetching page {page}: {url}")

            for attempt in range(1, 4):
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    break
                except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                    if attempt == 3:
                        raise RuntimeError(
                            f"wger request failed on page {page} after 3 attempts"
                        ) from exc
                    delay = attempt * 2
                    print(f"  Request failed (attempt {attempt}/3), retrying in {delay}s...")
                    time.sleep(delay)

            data = resp.json()
            page_results = data.get("results", [])
            if not isinstance(page_results, list):
                raise RuntimeError(f"Invalid wger payload on page {page}: results is not a list")
            results.extend(page_results)

            print(f"  Page {page}: got {len(page_results)} exercises (total: {len(results)})")

            url = data.get("next")  # None khi hết trang

    unique: dict[int, dict] = {}
    for exercise in results:
        if not isinstance(exercise, dict):
            continue
        try:
            exercise_id = int(exercise["id"])
        except (KeyError, TypeError, ValueError):
            continue
        unique.setdefault(exercise_id, exercise)
    return [unique[exercise_id] for exercise_id in sorted(unique)]


def _write_json_atomic(path: Path, exercises: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(exercises, output, ensure_ascii=False, indent=2)
        output.write("\n")
    temporary_path.replace(path)


def main():
    print("=== Fetching exercises from wger.de ===")
    print("Outputs:")
    for path in OUTPUT_PATHS:
        print(f"- {path}")
    print()

    exercises = fetch_all_exercises()

    print(f"\nTotal exercises fetched: {len(exercises)}")

    for path in OUTPUT_PATHS:
        _write_json_atomic(path, exercises)
        print(f"Saved to: {path}")


if __name__ == "__main__":
    main()
