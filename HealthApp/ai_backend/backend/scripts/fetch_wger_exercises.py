"""
Script cào dữ liệu bài tập từ wger.de API và lưu thành JSON.

Chạy: python scripts/fetch_wger_exercises.py
Output: backend/data/wger_exercises_raw.json
"""

import json
import time
from pathlib import Path

import httpx

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "wger_exercises_raw.json"
BASE_URL = "https://wger.de/api/v2"

# Chỉ lấy bài tập tiếng Anh (language=2)
ENDPOINT = f"{BASE_URL}/exerciseinfo/?format=json&language=2&limit=100"

TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=5.0)
HEADERS = {"User-Agent": "HealthApp/1.0"}


def fetch_all_exercises() -> list[dict]:
    results = []
    url = ENDPOINT
    page = 0

    with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        while url:
            page += 1
            print(f"  Fetching page {page}: {url}")

            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                print(f"  HTTP error on page {page}: {e}")
                break
            except httpx.TimeoutException:
                print(f"  Timeout on page {page}, retrying in 5s...")
                time.sleep(5)
                continue

            data = resp.json()
            page_results = data.get("results", [])
            results.extend(page_results)

            print(f"  Page {page}: got {len(page_results)} exercises (total: {len(results)})")

            url = data.get("next")  # None khi hết trang

    return results


def main():
    print("=== Fetching exercises from wger.de ===")
    print(f"Output: {OUTPUT_PATH}\n")

    exercises = fetch_all_exercises()

    print(f"\nTotal exercises fetched: {len(exercises)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(exercises, f, ensure_ascii=False, indent=2)

    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
