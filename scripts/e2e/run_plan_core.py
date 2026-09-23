"""Exercise the existing Plan V2 product API with two real Firebase principals.

This is an API/state subcheck for E2E-04/05/06/07/11, not a substitute for
their required browser trace. No credentials or tokens are persisted.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reset_real_auth_users import ALLOWED_UIDS, firebase_login  # noqa: E402


BASE = "http://127.0.0.1:8080"
FIRESTORE_BASE = "https://firestore.googleapis.com/v1/projects/healthcare-191d8/databases/(default)/documents"


def firestore_value(value):
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "arrayValue" in value:
        return [firestore_value(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {key: firestore_value(item) for key, item in value["mapValue"].get("fields", {}).items()}
    if "nullValue" in value:
        return None
    raise ValueError("UNKNOWN_FIRESTORE_VALUE_TYPE")


def fetch_profile(client: httpx.Client, uid: str, token: str) -> dict:
    response = client.get(f"{FIRESTORE_BASE}/nguoi_dung/{uid}", headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return {key: firestore_value(value) for key, value in response.json()["fields"].items()}


def request(client: httpx.Client, token: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    response = client.request(method, f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"}, json=body)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return response.status_code, payload


def require(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(label)


def plan_body(profile: dict, domain: str = "COMBINED_HEALTH") -> dict:
    start = date.today()
    workout = profile.get("workout_profile") or {}
    return {
        "domain": domain,
        "period_start": start.isoformat(),
        "period_end": (start + timedelta(days=6)).isoformat(),
        "timezone": "Asia/Ho_Chi_Minh",
        "profile": {
            "age": profile["age"],
            "gender": profile.get("gender"),
            "equation_sex": profile.get("equation_sex"),
            "nutrition_safety_profile": profile.get("nutrition_safety_profile", {}),
            "height": profile["height"],
            "weight": profile["weight"],
            "activity_level": profile["activityLevel"],
            "health_goal": profile["healthGoal"],
            "nutrition_profile": profile.get("nutrition_profile"),
            "workout_profile": profile.get("workout_profile"),
            "health_profile": profile.get("health_profile"),
        },
        "number_of_sessions": workout.get("available_days_per_week"),
        "duration_minutes": workout.get("default_session_duration_minutes"),
        "training_location": workout.get("training_location"),
        "equipment": workout.get("available_equipment") or [],
        "temporary_preferences": [],
        "temporary_exclusions": [],
    }


def create_and_save(client: httpx.Client, token: str, profile: dict, label: str) -> dict:
    status, preview = request(client, token, "POST", "/api/plan-v2/previews", plan_body(profile))
    require(status == 200 and preview.get("status") == "READY", f"{label}_PREVIEW_NOT_READY:{status}:{preview.get('status')}")
    require(preview.get("preview_persistence_status") == "PERSISTED", f"{label}_PREVIEW_NOT_PERSISTED")
    print(f"{label}_PREVIEW=PASS")
    exact = {
        "plan_id": preview["plan_id"],
        "revision_id": preview["revision_id"],
        "revision_content_hash": preview["revision_content_hash"],
        "action_id": f"e2e-save-{uuid4()}",
    }
    status, saved = request(client, token, "POST", "/api/plan-v2/plans/save", exact)
    require(status == 200 and saved.get("read_back_verified") is True, f"{label}_SAVE_FAILED:{status}")
    require(saved["plan"]["revision_content_hash"] == exact["revision_content_hash"], f"{label}_HASH_CHANGED")
    require(saved["plan"]["lifecycle_status"] == "SAVED", f"{label}_SAVE_ACTIVATED")
    status, repeated = request(client, token, "POST", "/api/plan-v2/plans/save", exact)
    require(status == 200 and repeated["plan"]["revision_id"] == exact["revision_id"], f"{label}_SAVE_NOT_IDEMPOTENT:{status}")
    status, readback = request(client, token, "GET", f"/api/plan-v2/plans/{exact['plan_id']}?revision_id={exact['revision_id']}")
    require(status == 200 and readback["plan"]["revision_content_hash"] == exact["revision_content_hash"], f"{label}_READBACK_MISMATCH")
    print(f"{label}_SAVE_READBACK_IDEMPOTENCY=PASS")
    return {**exact, "presentation": saved["plan"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-security", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("E2E_TEST_PASSWORD") or getpass.getpass("E2E test password: ")
    emails = {
        alias: os.environ.get(f"E2E_TEST_EMAIL_{alias}") or input(f"Email for user {alias}: ").strip()
        for alias in ALLOWED_UIDS
    }
    tokens = {alias: firebase_login(emails[alias], password, uid) for alias, uid in ALLOWED_UIDS.items()}
    with httpx.Client(timeout=185) as client:
        profiles = {alias: fetch_profile(client, uid, tokens[alias]) for alias, uid in ALLOWED_UIDS.items()}
        for alias, profile in profiles.items():
            complete = bool(profile.get("basic_profile_completed_at") and profile.get("health_profile"))
            print(f"USER_{alias}_AUTH=PASS PROFILE_COMPLETE={complete}")
            if not complete:
                raise RuntimeError("PROFILE_PRECONDITION_FAILED")
        baseline = {}
        for alias in ALLOWED_UIDS:
            status, payload = request(client, tokens[alias], "GET", "/api/plan-v2/plans")
            print(f"USER_{alias}_PLAN_BASELINE_HTTP={status} COUNT={len(payload.get('plans', []))}")
            if status != 200:
                raise RuntimeError("PLAN_BASELINE_READ_FAILED")
            baseline[alias] = payload.get("plans", [])

        if args.resume_security:
            require(all(baseline[alias] for alias in ("A", "B")), "SAVED_PLAN_REQUIRED_TO_RESUME")
            plans = {
                alias: {key: baseline[alias][-1][key] for key in ("plan_id", "revision_id", "revision_content_hash")}
                for alias in ("A", "B")
            }
        else:
            plans = {
                alias: create_and_save(client, tokens[alias], profiles[alias], alias)
                for alias in ("A", "B")
            }
        for owner, other in (("A", "B"), ("B", "A")):
            target = plans[owner]
            status, denied = request(client, tokens[other], "GET", f"/api/plan-v2/plans/{target['plan_id']}?revision_id={target['revision_id']}")
            require(status == 404 and "plan" not in denied, f"CROSS_OWNER_READ_LEAK:{owner}:{status}")
            status, denied = request(client, tokens[other], "POST", "/api/plan-v2/plans/save", {**target, "action_id": f"foreign-{uuid4()}"})
            require(status in (403, 404) and "plan" not in denied, f"CROSS_OWNER_WRITE_LEAK:{owner}:{status}")
            status, readback = request(client, tokens[owner], "GET", f"/api/plan-v2/plans/{target['plan_id']}?revision_id={target['revision_id']}")
            require(status == 200 and readback["plan"]["revision_content_hash"] == target["revision_content_hash"], f"CROSS_OWNER_TARGET_MUTATED:{owner}")
        print("CROSS_OWNER_BOTH_DIRECTIONS=PASS")

        target = plans["A"]
        for operation, expected in (("activate", "ACTIVE"), ("pause", "PAUSED")):
            status, changed = request(client, tokens["A"], "POST", f"/api/plan-v2/plans/{target['plan_id']}/revisions/{target['revision_id']}/{operation}", {
                "expected_revision_number": 1,
                "action_id": f"e2e-{operation}-{uuid4()}",
            })
            require(status == 200 and changed["plan"]["lifecycle_status"] == expected, f"LIFECYCLE_{operation.upper()}_FAILED:{status}")
            status, readback = request(client, tokens["A"], "GET", f"/api/plan-v2/plans/{target['plan_id']}")
            require(status == 200 and readback["plan"]["lifecycle_status"] == expected, f"LIFECYCLE_{operation.upper()}_READBACK_FAILED")
        status, history = request(client, tokens["A"], "GET", f"/api/plan-v2/plans/{target['plan_id']}/history")
        require(status == 200 and history.get("history"), "HISTORY_MISSING")
        print("PLAN_LIFECYCLE_READBACK=PASS")


if __name__ == "__main__":
    main()
