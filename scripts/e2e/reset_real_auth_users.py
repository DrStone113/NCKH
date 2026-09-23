"""Fail-closed reset for the two dedicated live Firebase E2E principals.

Dry-run is the default. The password is read from E2E_TEST_PASSWORD or a
terminal prompt; no password or token is accepted on the command line or
written to an artifact. --apply requires the exact Firebase UID a second time.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import sys
from pathlib import Path

import asyncpg
import httpx


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend"))
from config import settings  # noqa: E402


ALLOWED_UIDS = {
    "A": "EnKH887NJzWMxfssLOhUHMjI0xI3",
    "B": "prZstfPO1KYHIvB09Jcy0qvII1N2",
}
FIRESTORE_COLLECTIONS = (
    "chi_so_co_the",
    "nhat_ky_an_uong",
    "nhat_ky_tap_luyen",
    "lifestyle_logs",
    "lifestyle_reminders",
    "water_intake",
)
SQL_OWNED_TABLES = {
    "chat_sessions": "user_id",
    "plans": "user_id",
    "user_facts": "user_id",
    "workout_plans_e4": "user_id",
    "workout_plan_previews_e4": "owner_user_id",
    "plan_v2_active_claims": "owner_user_id",
    "plan_v2_attach_actions": "owner_user_id",
    "plan_v2_change_events": "owner_user_id",
    "plan_v2_pending_actions": "owner_user_id",
    "plan_v2_plans": "owner_user_id",
    "plan_v2_preview_actions": "owner_user_id",
    "plan_v2_previews": "owner_user_id",
    "plan_v2_revisions": "owner_user_id",
    "plan_v2_write_actions": "owner_user_id",
    "nutrition_personal_memory_n3": "owner_user_id",
    "nutrition_personal_portion_corrections_n3_2": "owner_user_id",
    "nutrition_personal_portion_observations_n3_2": "owner_user_id",
    "nutrition_personal_recipes_n3": "owner_user_id",
    "nutrition_preference_profile_n3_2": "owner_user_id",
    "nutrition_recipe_candidates_n3": "owner_user_id",
    "nutrition_recipe_feedback_n3": "owner_user_id",
    "nutrition_recommendation_feedback_n3_2": "owner_user_id",
    "nutrition_recommendation_memory_n3_2": "owner_user_id",
}
UNSUPPORTED_OWNER_TABLES = {
    "nutrition_personal_recipes_n3",
    "nutrition_recipe_candidates_n3",
    "nutrition_recipe_feedback_n3",
}


def firebase_api_key() -> str:
    source = (ROOT / "apps" / "mobile" / "lib" / "firebase_options.dart").read_text(encoding="utf-8")
    match = re.search(r"apiKey:\s*'([^']+)'", source)
    if not match:
        raise RuntimeError("FIREBASE_WEB_API_KEY_NOT_FOUND")
    return match.group(1)


def firebase_login(email: str, password: str, expected_uid: str) -> str:
    response = httpx.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
        params={"key": firebase_api_key()},
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("localId") != expected_uid:
        raise RuntimeError("FIREBASE_UID_ALLOWLIST_MISMATCH")
    return payload["idToken"]


def firestore_inventory(uid: str, token: str) -> tuple[bool, dict[str, list[str]]]:
    base = "https://firestore.googleapis.com/v1/projects/healthcare-191d8/databases/(default)/documents"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        profile = client.get(f"{base}/nguoi_dung/{uid}", headers=headers)
        if profile.status_code not in (200, 404):
            profile.raise_for_status()
        owned: dict[str, list[str]] = {}
        for collection in FIRESTORE_COLLECTIONS:
            query = {
                "structuredQuery": {
                    "from": [{"collectionId": collection}],
                    "where": {
                        "fieldFilter": {
                            "field": {"fieldPath": "userId"},
                            "op": "EQUAL",
                            "value": {"stringValue": uid},
                        }
                    },
                }
            }
            response = client.post(f"{base}:runQuery", headers=headers, json=query)
            response.raise_for_status()
            names: list[str] = []
            for row in response.json():
                document = row.get("document")
                if not document:
                    continue
                name = document.get("name", "")
                actual_owner = document.get("fields", {}).get("userId", {}).get("stringValue")
                if actual_owner != uid or f"/documents/{collection}/" not in name:
                    raise RuntimeError("FIRESTORE_OWNER_OR_COLLECTION_MISMATCH")
                names.append(name)
            owned[collection] = names
        return profile.status_code == 200, owned


async def sql_inventory(uid: str) -> dict[str, int]:
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn=dsn)
    try:
        counts = {
            table: await connection.fetchval(f"SELECT count(*) FROM {table} WHERE {column} = $1", uid)
            for table, column in SQL_OWNED_TABLES.items()
        }
        discovered = await connection.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name IN ('user_id','owner_user_id')"
        )
        for row in discovered:
            table, column = row["table_name"], row["column_name"]
            if table not in SQL_OWNED_TABLES:
                count = await connection.fetchval(
                    f"SELECT count(*) FROM {table} WHERE {column} = $1", uid
                )
                if count:
                    raise RuntimeError(f"UNHANDLED_OWNED_TABLE:{table}")
        if any(counts[table] for table in UNSUPPORTED_OWNER_TABLES):
            raise RuntimeError("RECIPE_SHADOW_ROWS_REQUIRE_EXPLICIT_REVIEW")
        return counts
    finally:
        await connection.close()


async def reset_sql(uid: str) -> None:
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(dsn=dsn)
    try:
        async with connection.transaction():
            statements = (
                "DELETE FROM plan_v2_active_claims WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_attach_actions WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_change_events WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_preview_actions WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_pending_actions WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_write_actions WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_items WHERE revision_id IN (SELECT id FROM plan_v2_revisions WHERE owner_user_id=$1)",
                "UPDATE plan_v2_revisions SET parent_revision_id=NULL WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_revisions WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_previews WHERE owner_user_id=$1",
                "DELETE FROM plan_v2_plans WHERE owner_user_id=$1",
                "DELETE FROM plans WHERE user_id=$1",
                "DELETE FROM workout_plan_previews_e4 WHERE owner_user_id=$1",
                "DELETE FROM workout_plans_e4 WHERE user_id=$1",
                "DELETE FROM user_facts WHERE user_id=$1",
                "DELETE FROM chat_sessions WHERE user_id=$1",
                "DELETE FROM nutrition_catalog_gap_feedback_evidence_n3_2 WHERE feedback_event_id IN (SELECT id FROM nutrition_recommendation_feedback_n3_2 WHERE owner_user_id=$1)",
                "DELETE FROM nutrition_shadow_policy_logs_n3_2 WHERE recommendation_event_id IN (SELECT id FROM nutrition_recommendation_memory_n3_2 WHERE owner_user_id=$1)",
                "DELETE FROM nutrition_personal_portion_corrections_n3_2 WHERE owner_user_id=$1",
                "DELETE FROM nutrition_personal_portion_observations_n3_2 WHERE owner_user_id=$1",
                "DELETE FROM nutrition_recommendation_feedback_n3_2 WHERE owner_user_id=$1",
                "DELETE FROM nutrition_recommendation_memory_n3_2 WHERE owner_user_id=$1",
                "DELETE FROM nutrition_preference_profile_n3_2 WHERE owner_user_id=$1",
                "DELETE FROM nutrition_personal_memory_n3 WHERE owner_user_id=$1",
            )
            for statement in statements:
                await connection.execute(statement, uid)
    finally:
        await connection.close()


def reset_firestore(uid: str, token: str, owned: dict[str, list[str]], include_profile: bool) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        for collection, names in owned.items():
            for name in names:
                if f"/documents/{collection}/" not in name:
                    raise RuntimeError("FIRESTORE_PATH_SCOPE_MISMATCH")
                response = client.delete(f"https://firestore.googleapis.com/v1/{name}", headers=headers)
                response.raise_for_status()
        if include_profile:
            response = client.delete(
                f"https://firestore.googleapis.com/v1/projects/healthcare-191d8/databases/(default)/documents/nguoi_dung/{uid}",
                headers=headers,
            )
            if response.status_code not in (200, 404):
                response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", choices=tuple(ALLOWED_UIDS), required=True)
    parser.add_argument("--apply", action="store_true", help="perform deletion after preflight")
    parser.add_argument("--confirm-uid", help="required exact UID when --apply is used")
    parser.add_argument("--include-profile", action="store_true", help="also delete the test user's onboarding profile")
    args = parser.parse_args()
    uid = ALLOWED_UIDS[args.user]
    if args.apply and args.confirm_uid != uid:
        raise SystemExit("CONFIRM_UID_MISMATCH")
    email = os.environ.get(f"E2E_TEST_EMAIL_{args.user}") or input(f"Email for test user {args.user}: ").strip()
    password = os.environ.get("E2E_TEST_PASSWORD") or getpass.getpass("E2E test password: ")
    token = firebase_login(email, password, uid)
    profile_exists, firestore = firestore_inventory(uid, token)
    sql = asyncio.run(sql_inventory(uid))
    print(f"USER={args.user} AUTH=PASS PROFILE_EXISTS={profile_exists}")
    print("FIRESTORE_COUNTS=" + ",".join(f"{key}:{len(value)}" for key, value in firestore.items()))
    print("SQL_COUNTS=" + ",".join(f"{key}:{value}" for key, value in sql.items() if value))
    if not args.apply:
        print("RESET=DRY_RUN_ONLY")
        return
    asyncio.run(reset_sql(uid))
    reset_firestore(uid, token, firestore, args.include_profile)
    print("RESET=PASS")


if __name__ == "__main__":
    main()
