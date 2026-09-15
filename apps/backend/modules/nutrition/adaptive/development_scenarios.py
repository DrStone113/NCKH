"""Engineering-only N3.2 scenarios; they are not research benchmark cases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class N32DevelopmentScenario:
    scenario_id: str
    focus: str
    expected_invariants: tuple[str, ...]


def development_scenarios() -> tuple[N32DevelopmentScenario, ...]:
    return (
        N32DevelopmentScenario("N32_COLD_START", "cold start", ("PREFERENCE_EVIDENCE_INSUFFICIENT",)),
        N32DevelopmentScenario("N32_RICH_HISTORY", "rich history", ("SOFT_PREFERENCE_ONLY",)),
        N32DevelopmentScenario("N32_CONFLICTING_PREFERENCE", "explicit/inferred conflict", ("PREFERENCE_CONFLICT",)),
        N32DevelopmentScenario("N32_EXPLICIT_DISLIKE", "explicit dislike", ("EXPLICIT_FACT_WINS",)),
        N32DevelopmentScenario("N32_TEMPORARY_REJECTION", "not today", ("NOT_PERMANENT_DISLIKE",)),
        N32DevelopmentScenario("N32_REPEAT_DISH", "repeat dish", ("SOFT_DIVERSITY_PENALTY",)),
        N32DevelopmentScenario("N32_REPEAT_PROTEIN", "repeat protein", ("SOFT_DIVERSITY_PENALTY",)),
        N32DevelopmentScenario("N32_NEW_CUISINE", "bounded novelty", ("HARD_FILTER_FIRST",)),
        N32DevelopmentScenario("N32_PERSONAL_RECIPE", "private recipe", ("PERSONAL_SCOPE_ONLY",)),
        N32DevelopmentScenario("N32_PORTION_CORRECTION", "portion learning", ("ACTUAL_LOG_REQUIRED",)),
        N32DevelopmentScenario("N32_CATALOG_GAP", "gap evidence", ("AGGREGATE_ONLY",)),
        N32DevelopmentScenario("N32_EXTERNAL_CANDIDATE", "runtime external", ("SOURCE_QUALITY_APPLIED",)),
        N32DevelopmentScenario("N32_STAGING_CANDIDATE", "staging external", ("SHADOW_ONLY",)),
        N32DevelopmentScenario("N32_NO_FEASIBLE", "no feasible candidate", ("NO_HARD_CONSTRAINT_BYPASS",)),
        N32DevelopmentScenario("N32_WEB_UNAVAILABLE", "discovery unavailable", ("LOCAL_FALLBACK_OR_TYPED_FAILURE",)),
    )


__all__ = ["N32DevelopmentScenario", "development_scenarios"]
