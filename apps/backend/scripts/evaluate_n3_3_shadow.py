"""N3.3 read-only inventory and development evidence; never a delivery path.

Prints aggregate JSON to stdout. It performs no writes, migrations, service
startup, feedback generation in PostgreSQL, or research benchmark execution.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))


async def durable_inventory() -> dict:
    import asyncpg
    from config import settings
    from sqlalchemy.engine import make_url

    result = {
        "evidence_type": "DURABLE_STORE_AGGREGATE_AUDIT",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "transaction": "REPEATABLE_READ_READ_ONLY",
        "real_usage_provenance": "UNVERIFIED_NO_ORIGIN_REGISTER",
        "real_counts": {key: None for key in (
            "REAL_RECOMMENDATION_EVENTS", "REAL_FEEDBACK_EVENTS", "USERS_WITH_FEEDBACK",
            "LIKED_EVENTS", "DISLIKED_EVENTS", "SAVED_EVENTS", "REJECTED_EVENTS",
        )},
        "observed_rates": None,
        "observed_comparisons": None,
        "counterfactual_policy_evaluation": "NOT_SUPPORTED",
    }
    connection = None
    try:
        url = make_url(settings.database_url)
        connection = await asyncpg.connect(
            host=url.host, port=url.port or 5432, user=url.username,
            password=url.password, database=url.database, timeout=5, command_timeout=10,
        )
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            tables = (
                "nutrition_recommendation_memory_n3_2",
                "nutrition_recommendation_feedback_n3_2",
                "nutrition_preference_profile_n3_2",
                "nutrition_personal_portion_observations_n3_2",
                "nutrition_personal_portion_corrections_n3_2",
                "nutrition_shadow_policy_logs_n3_2",
                "nutrition_catalog_gap_feedback_evidence_n3_2",
            )
            counts = {}
            for table in tables:  # fixed identifiers, no user-supplied SQL
                exists = await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", table)
                counts[table] = await connection.fetchval(f"SELECT count(*) FROM {table}") if exists else None
            result["unclassified_durable_table_counts"] = counts
            if any(value is None for value in counts.values()):
                result["status"] = "INCOMPLETE_SCHEMA_READ_ONLY_NO_MIGRATION"
                return result
            result["raw_event_counts_unverified_origin"] = {
                row["event_type"]: row["n"] for row in await connection.fetch(
                    "SELECT event_type, count(*) AS n FROM nutrition_recommendation_feedback_n3_2 GROUP BY event_type"
                )
            }
            result["raw_rejection_counts_unverified_origin"] = {
                row["rejection_reason"]: row["n"] for row in await connection.fetch(
                    "SELECT rejection_reason, count(*) AS n FROM nutrition_recommendation_feedback_n3_2 WHERE event_type='REJECTED' GROUP BY rejection_reason"
                )
            }
            result["feedback_identity_mismatch_count"] = await connection.fetchval("""
                SELECT count(*) FROM nutrition_recommendation_feedback_n3_2 f
                LEFT JOIN nutrition_recommendation_memory_n3_2 m ON m.id=f.recommendation_id
                WHERE m.id IS NULL OR f.owner_user_id IS DISTINCT FROM m.owner_user_id
                  OR f.candidate_id IS DISTINCT FROM m.candidate_id
                  OR f.policy_version IS DISTINCT FROM m.policy_version
            """)
            result["shadow_log_binding_counts"] = dict(await connection.fetchrow("""
                SELECT count(*) AS logs, count(recommendation_event_id) AS recommendation_bound,
                       count(production_selected_candidate_id) AS delivered_identity,
                       count(outcome_event) AS outcomes, count(selection_probability) AS numeric_probability_fields
                FROM nutrition_shadow_policy_logs_n3_2
            """))
            if not counts[tables[0]] and not counts[tables[1]]:
                result["real_counts"] = dict.fromkeys(result["real_counts"], 0)
                result["real_usage_provenance"] = "EMPTY_DURABLE_STORE"
            result["status"] = "READ_ONLY_AGGREGATES_AVAILABLE"
    except (OSError, TimeoutError, asyncpg.PostgresError) as exc:
        # Exception messages/DSNs can contain credentials or personal values.
        result["status"] = "DATABASE_UNAVAILABLE"
        result["error_type"] = type(exc).__name__
        result["os_error_code"] = getattr(exc, "winerror", None)
    finally:
        if connection is not None:
            await connection.close()
    return result


def freeze_inventory() -> dict:
    from modules.nutrition.adaptive.shadow_evaluation import frozen_ranking_baselines
    from modules.nutrition.adaptive.intelligence import PreferenceProfileBuilder, ShadowBanditPolicy
    components = []
    for item in frozen_ranking_baselines():
        row = asdict(item)
        row["source_sha256"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in item.source_paths}
        components.append(row)
    return {
        "purpose": "PRODUCT_ENGINEERING_SHADOW_ONLY",
        "components": components,
        "preference_event_affinities": {key.value: value for key, value in PreferenceProfileBuilder._EVENT_AFFINITY.items()},
        "preference_half_life_days": PreferenceProfileBuilder.half_life_days,
        "shadow_bandit_reward_policy": {key.value: value for key, value in ShadowBanditPolicy._REWARDS.items()},
        "production_adaptive_ranking": False,
        "canonical_auto_promotion": False,
    }


def canonical_development_replay() -> list[dict]:
    """Source-derived A order, with top-1 checked against real suggest_dish.

    Contexts are synthetic. Catalog reads are current product data, never
    evidence of observed exposure, user feedback, or research performance.
    No GPS/recent-history options are used in these three bounded probes.
    """
    from modules.nutrition.adaptive.contracts import ConstraintContext
    from modules.nutrition.adaptive.delivery import canonical_catalog_reference, TrustedDeliveryError
    from modules.nutrition.adaptive.intelligence import RecommendationContext
    from modules.nutrition.adaptive.shadow_evaluation import ShadowComparisonScenario, evaluate_shadow_comparison
    from modules.nutrition.canonical_foods import load_canonical_food_catalog
    from services.agent.tools import dish

    foods = frozenset(str(row["food_id"]) for row in load_canonical_food_catalog())
    results = []
    for meal_type, target, query in (("lunch", 500, ""), ("dinner", 600, "gà"), ("breakfast", 400, "")):
        selected = dish.suggest_dish(meal_type, target, query=query)
        scaled = [
            row for record in dish._DISHES
            if meal_type in record.meal_types and
            (not query or dish._remove_accents(query) in dish._remove_accents(record.name.lower()))
            for row in (dish._scale_dish(record, target),) if row is not None
        ]
        scaled.sort(key=lambda row: (abs(row.scale_factor - 1), abs(row.total_calories - target), row.record.id))
        assert scaled[0].record.id == selected["id"], "FROZEN_BASELINE_CAPTURE_MISMATCH"
        candidates = []
        excluded = 0
        for row in scaled:
            try:
                candidate = canonical_catalog_reference({
                    "id": row.record.id, "name": row.record.name,
                    "components": [dict(component) for component in row.components],
                    "total_calories": row.total_calories, "total_protein": row.total_protein,
                    "total_carbs": row.total_carbs, "total_fat": row.total_fat,
                    "dietary_tags": {"objective": sorted(row.record.objective_tags)},
                })
            except TrustedDeliveryError:
                excluded += 1
                continue
            candidates.append(candidate)
        candidate_ids = tuple(row.candidate_id for row in candidates)
        comparison = evaluate_shadow_comparison(ShadowComparisonScenario(
            f"N33_CANONICAL_{meal_type.upper()}", tuple(candidates),
            RecommendationContext(meal_type=meal_type, constraints=ConstraintContext(target_kcal=target)),
            candidate_ids, owner_user_id="n33-synthetic-catalog-context",
            expected_valid_candidate_ids=frozenset(candidate_ids), canonical_food_ids=foods,
        ))
        results.append({
            "comparison": asdict(comparison),
            "baseline_origin": "SOURCE_DERIVED_ORDER_TOP1_VERIFIED_AGAINST_SUGGEST_DISH",
            "baseline_top1_matches_actual_tool": bool(candidates) and candidates[0].source.source_recipe_id == str(selected["id"]),
            "eligible_candidates": len(candidates), "projection_exclusions": excluded,
            "meal_type": meal_type, "target_kcal": target, "query": query,
            "user_feedback_used": 0, "objective_preference_ground_truth": None,
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inventory", "durable", "development"))
    mode = parser.parse_args().mode
    if mode == "durable":
        result = asyncio.run(durable_inventory())
    elif mode == "inventory":
        result = freeze_inventory()
    else:
        # Fixtures live in the focused test file, never the runtime data store.
        namespace = runpy.run_path(str(BACKEND / "tests/test_n3_3_adaptive_ranking_shadow_evaluation.py"))
        result = namespace["development_evidence"]()
        result["canonical_catalog_replays"] = canonical_development_replay()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, default=str))


if __name__ == "__main__":
    main()
