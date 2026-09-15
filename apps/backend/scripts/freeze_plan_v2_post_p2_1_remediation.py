"""Freeze the distinct P2.2 implementation identity; never rewrite P2.1."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation" / "plan_tool_v2_p2"
OUTPUT = VALIDATION / "plan-v2-post-p2-1-remediation-v1.json"

SOURCES = (
    "services/plan_engine/contracts.py",
    "services/plan_engine/engine.py",
    "services/plan_engine/lifecycle.py",
    "services/plan_engine/persistence.py",
    "services/agent/pending_user_action.py",
    "services/agent/tools/plan_v2.py",
    "modules/plans/v2_router.py",
    "main.py",
)
MIGRATIONS = tuple(f"db/migrations/{index:03d}_{name}" for index, name in (
    (10, "plan_tool_v2.sql"),
    (11, "plan_tool_v2_p2_enforced.sql"),
    (12, "plan_tool_v2_p2_item_order.sql"),
    (13, "plan_tool_v2_p2_logical_item_identity.sql"),
    (14, "adaptive_nutrition_knowledge_n3.sql"),
    (15, "external_recipe_discovery_n3_1.sql"),
    (16, "adaptive_recommendation_intelligence_n3_2.sql"),
))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    v3_manifest = json.loads((VALIDATION / "plan-v2-confirmatory-v3-freeze-manifest-v1.json").read_text(encoding="utf-8"))
    forensic = VALIDATION / "p2-2-p2-1-forensic-status-v1.json"
    edge = VALIDATION / "p2-2-authenticated-edge-e2e-v1.json"
    edge_record = json.loads(edge.read_text(encoding="utf-8"))
    if edge_record.get("status") != "PASS":
        raise RuntimeError("AUTHENTICATED_EDGE_E2E_NOT_PASS")
    return {
        "baseline_version": "PLAN_V2_POST_P2_1_REMEDIATION_V1",
        "baseline_status": "FROZEN_FOR_CONFIRMATORY_V3_ONLY",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "p2_1_boundary": {
            "first_pass_result": "FAIL",
            "dataset_status": "USED_FOR_TUNING_AFTER_FIRST_PASS",
            "forensic_status_sha256": _sha(forensic),
            "not_the_p2_1_implementation_identity": True,
        },
        "implementation_sources": {path: _sha(ROOT / path) for path in SOURCES},
        "migration_checksums": {path: _sha(ROOT / path) for path in MIGRATIONS},
        "policy_versions": {
            "nutrition": "nutrition-policy-v1.0.1",
            "exercise": "exercise-prescription-policy-v1.1.0",
            "canonical_nutrition_authority": True,
            "n3_adaptive_ranking_isolation": "DEVELOPMENT_SHADOW_ONLY",
        },
        "toolchain": {
            "python": platform.python_version(),
            "flutter": "3.44.8",
            "dart": "3.12.2",
            "postgresql": "16.15",
        },
        "authenticated_browser_evidence": {
            "path": edge.name,
            "sha256": _sha(edge),
            "status": edge_record["status"],
        },
        "confirmatory_v3_dependency": {
            "manifest_path": "plan-v2-confirmatory-v3-freeze-manifest-v1.json",
            "manifest_sha256": _sha(VALIDATION / "plan-v2-confirmatory-v3-freeze-manifest-v1.json"),
            "holdout_sha256": v3_manifest["artifacts"]["plan-v2-confirmatory-v3.json"],
            "oracle_sha256": v3_manifest["artifacts"]["plan-v2-confirmatory-oracle-v3.json"],
            "threshold_sha256": v3_manifest["artifacts"]["plan-v2-confirmatory-thresholds-v3.json"],
            "execution_status": "FROZEN_UNEXECUTED",
        },
    }


def main() -> int:
    payload = build()
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"baseline": payload["baseline_version"], "sha256": _sha(OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
