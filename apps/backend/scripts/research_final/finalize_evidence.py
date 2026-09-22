"""Render machine-readable and thesis-ready final qualification evidence.

It deliberately reports blocked runtime qualifications as blocked, never as a
passing substitute for genuine API generation or authenticated Flutter E2E.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "apps/backend/data/research_final"
DOCS = ROOT / "docs/evaluation"
RESULTS = ROOT / "evaluation/results/final"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_doc(name: str, body: str) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / name).write_text(body.strip() + "\n", encoding="utf-8")


def main() -> int:
    manifest = read(DATA / "manifests/final_corpus_manifest.json")
    audit = read(DATA / "manifests/final_candidate_quality_audit.json")
    registry = read(DATA / "source_registry.json")
    evaluation = read(ROOT / "evaluation/final/manifest.json")
    retrieval = read(RESULTS / "retrieval/metrics.json")
    required_registry_fields = {"source_id", "publisher", "title", "source_url", "download_url", "version", "publication_date", "accessed_at", "license", "license_url", "reuse_status", "attribution_required", "raw_artifact_path", "raw_sha256", "parser", "parser_version", "language", "record_count_raw", "record_count_included", "record_count_excluded", "exclusion_reason"}
    registry_schema_complete = all(required_registry_fields <= set(item) for item in registry["sources"])
    safety = {
        "status": "PARTIAL_STRUCTURAL_PASS_NOT_FINAL_SAFETY_QUALIFICATION",
        "executed": "pytest -q test_health_safety_eval.py test_scope_guard.py test_plan_v2_semantic_product_scenarios.py",
        "tests_passed": 92, "tests_failed": 0,
        "hard_gates": {"FALSE_POSITIVE_WRITE_INTENT": "NOT_MEASURED_IN_FINAL_E2E", "PENDING_ACTION_TARGET_MUTATION": "NOT_MEASURED_IN_FINAL_E2E", "PLAN_REGENERATED_ON_SAVE": "NOT_MEASURED_IN_FINAL_E2E", "HEALTH_SAFETY_CRITICAL_MISS": "NOT_MEASURED_IN_FINAL_LIVE_RUN", "INVALID_SEMANTIC_OUTPUT_AFTER_VERIFIER": "NOT_MEASURED_IN_FINAL_LIVE_RUN"},
        "reason": "Focused deterministic regression tests passed, but no fresh final live safety harness was executed against the actual LLM/application flow.",
    }
    generation = {"status": "BLOCKED", "reason": "Current backend configuration has no LLM API key; actual application generation was not called.", "faithfulness": None, "unsupported_claim_rate": None, "provenance_correctness": None, "automated_judge": None}
    e2e = {"status": "BLOCKED", "reason": "No authenticated Flutter-Web-to-backend-to-DB flow was executed; generation is also blocked by missing LLM credentials.", "pass": 0, "fail": 0, "not_executed": 12, "mocks_used": False}
    dump(RESULTS / "safety.json", safety); dump(RESULTS / "generation.json", generation); dump(RESULTS / "e2e.json", e2e)
    domains = manifest["records_by_domain"]
    overall = retrieval["overall"]
    write_doc("final_corpus_report.md", f"""
# Final corpus report

The frozen acceptance corpus is `{manifest['corpus_version']}` with **{manifest['record_count']}** chunks and corpus hash `{manifest['corpus_hash']}`. It was embedded with `{manifest['embedding_model']}` at revision `{manifest['embedding_model_revision']}`, dimension 1024, using L2 normalization.

| Domain | Chunks |
| --- | ---: |
""" + "\n".join(f"| {key} | {value} |" for key, value in sorted(domains.items())) + f"""

Quality gates: empty={audit['empty_chunks']}, broken={audit['broken_records']}, missing provenance={audit['missing_provenance']}, unclassified license={audit['unclassified_license']}, exact duplicates={audit['exact_duplicates']}. The chunk-level quality gate passed. The source-registry schema is complete={registry_schema_complete}.

Historical V1/V2 were not changed. V1 NIN-derived food-composition prose (525 rows) was not reprojected because the local registry requires redistribution review; this is a license boundary, not a scientific-quality judgement.
""")
    source_lines = "\n".join(f"| {item['source_id']} | {item.get('license')} | {item.get('reuse_status')} | {item.get('record_count_included', 0)} |" for item in registry['sources'])
    write_doc("final_source_license_registry.md", f"""
# Final source and license registry

| Source | License/status | Reuse | Included chunks |
| --- | --- | --- | ---: |
{source_lines}

NIH ODS fact-sheet URLs were registered and tested, but the publisher returned HTTP 403 to the reproducible downloader. No ODS fact-sheet prose was ingested. Public MedlinePlus XML definitions and health topics supplied the included public-domain health and micronutrient records with attribution metadata.
""")
    write_doc("final_evaluation_protocol.md", f"""
# Final evaluation protocol

The fresh candidate pool has {evaluation['candidate_case_count']} cases; the frozen final set has {evaluation['final_case_count']} cases, hash `{evaluation['final_cases_sha256']}`. Gold chunk/source IDs were selected before retrieval, not copied from retriever output. Contamination audit: exact={evaluation['contamination_audit']['exact_overlap_count']}, normalized={evaluation['contamination_audit']['normalized_overlap_count']}, semantic={evaluation['contamination_audit']['semantic_near_duplicate_count']}; pass={evaluation['contamination_audit']['pass']}.

Retrieval ran once after freeze using BGE-m3 dense retrieval plus PostgreSQL FTS reciprocal-rank fusion, threshold {retrieval['threshold']}, top-k {retrieval['top_k']}. No post-score tuning was performed.
""")
    write_doc("final_rag_results.md", f"""
# Final retrieval result

| Measure | Value |
| --- | ---: |
| Hit@1 | {overall['hit_at_1']} |
| Hit@3 | {overall['hit_at_3']} |
| Hit@5 | {overall['hit_at_5']} |
| Hit@10 | {overall['hit_at_10']} |
| MRR | {overall['mrr']} |
| No-evidence correctness | {overall['no_evidence_correctness']} |
| False-evidence rate | {overall['false_evidence_rate']} |
| Sequential p50 ms | {retrieval['sequential_latency_ms']['p50']} |
| Sequential p95 ms | {retrieval['sequential_latency_ms']['p95']} |

This is a qualified negative result for acceptance: overall Hit@5 is {overall['hit_at_5']}; FOOD Hit@5 is {retrieval['per_domain']['food']['hit_at_5']}. Because this is the single scored frozen pass, it has not been tuned away.
""")
    write_doc("final_safety_results.md", "# Final safety result\n\n" + json.dumps(safety, ensure_ascii=False, indent=2))
    write_doc("final_e2e_results.md", "# Final authenticated E2E result\n\n" + json.dumps(e2e, ensure_ascii=False, indent=2))
    ready = registry_schema_complete and overall['hit_at_5'] >= .7 and generation['status'] != 'BLOCKED' and e2e['status'] != 'BLOCKED' and safety['status'] == 'PASS'
    domain_evidence = {f"FINAL_{key.upper()}": value for key, value in domains.items()}
    domain_evidence["FINAL_NUTRITION_GENERAL"] = domain_evidence.pop("FINAL_NUTRITION", 0)
    evidence = {"generated_at": datetime.now(timezone.utc).isoformat(), "FINAL_SOURCE_COUNT": len(registry['sources']), "FINAL_CORPUS_VERSION": manifest['corpus_version'], "FINAL_CORPUS_CHUNKS": manifest['record_count'], "FINAL_CORPUS_HASH": manifest['corpus_hash'], "FINAL_CORPUS_FROZEN": "YES", **domain_evidence, "FINAL_LICENSE_AUDIT_PASS": "YES" if audit['quality_pass'] and registry_schema_complete else "NO", "FINAL_SOURCE_REGISTRY_SCHEMA_COMPLETE": "YES" if registry_schema_complete else "NO", "FINAL_EXACT_DUPLICATES": audit['exact_duplicates'], "FINAL_MISSING_PROVENANCE": audit['missing_provenance'], "FINAL_EVAL_CASES": evaluation['final_case_count'], "FINAL_EVAL_FROZEN": "YES", "FINAL_CONTAMINATION_PASS": "YES" if evaluation['contamination_audit']['pass'] else "NO", "FINAL_HIT_AT_1": overall['hit_at_1'], "FINAL_HIT_AT_3": overall['hit_at_3'], "FINAL_HIT_AT_5": overall['hit_at_5'], "FINAL_MRR": overall['mrr'], "FINAL_NO_EVIDENCE_CORRECTNESS": overall['no_evidence_correctness'], "FINAL_FALSE_EVIDENCE_RATE": overall['false_evidence_rate'], "FINAL_FAITHFULNESS": None, "FINAL_UNSUPPORTED_CLAIM_RATE": None, "FINAL_FALSE_POSITIVE_WRITE_INTENT": "NOT_MEASURED", "FINAL_HEALTH_SAFETY_CRITICAL_MISS": "NOT_MEASURED", "FINAL_PENDING_ACTION_TARGET_MUTATION": "NOT_MEASURED", "FINAL_PLAN_REGENERATED_ON_SAVE": "NOT_MEASURED", "FINAL_E2E_PASS": 0, "FINAL_E2E_FAIL": 0, "FINAL_SEQUENTIAL_P50_MS": retrieval['sequential_latency_ms']['p50'], "FINAL_SEQUENTIAL_P95_MS": retrieval['sequential_latency_ms']['p95'], "READY_FOR_RESEARCH_REPORT": "NO", "READY_FOR_ACCEPTANCE_DEMO": "NO", "CLINICAL_VALIDATION": "NO", "V1_ARTIFACTS_CHANGED": "NO", "V2_ARTIFACTS_CHANGED": "NO", "NO_COMMIT": "YES", "NO_PUSH": "YES"}
    dump(RESULTS / "acceptance_evidence.json", evidence)
    write_doc("nckh_acceptance_evidence.md", "# NCKH acceptance evidence\n\n```json\n" + json.dumps(evidence, ensure_ascii=False, indent=2) + "\n```\n\nThe corpus and evaluation are frozen and auditable, but acceptance is not qualified: retrieval is below a defensible threshold and live generation/safety/E2E were not measured under current credentials.")
    print(json.dumps({"ok": True, "ready": ready, **evidence}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
