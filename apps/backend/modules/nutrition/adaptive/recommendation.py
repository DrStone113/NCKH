"""Compatibility facade for the single N3.2 recommendation ranking contract.

``AdaptiveRecommendationPipeline`` remains for N3 callers, but it no longer
owns a second score formula. All soft score components now come from
``RecommendationRankerV2``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from .contracts import CandidateStatus, ConstraintContext, RecipeCandidate, TrustDomain
from .intelligence import (
    CandidateSourceType,
    PreferenceDimension,
    PreferenceEvidence,
    PreferenceSource,
    RecommendationContext,
    RecommendationMemoryEntry,
    RecommendationRankerV2,
    UserPreferenceProfile,
)


@dataclass(frozen=True)
class RankedRecipeCandidate:
    candidate: RecipeCandidate
    score: float
    public_trace: tuple[str, ...]


class AdaptiveRecommendationPipeline:
    """N3 shadow facade delegating its ranking to ``RecommendationRankerV2``."""

    def __init__(self, *, ranker: RecommendationRankerV2 | None = None) -> None:
        self._ranker = ranker or RecommendationRankerV2()

    def rank_shadow(
        self,
        candidates: Iterable[RecipeCandidate],
        *,
        constraints: ConstraintContext,
        preference_scores: Mapping[str, float] | None = None,
        recent_candidate_ids: Sequence[str] = (),
    ) -> list[RankedRecipeCandidate]:
        # N3 continues to be staging-only in this backwards-compatible entry
        # point. N3.2's ranker itself supports the explicit source mix.
        staging = [
            candidate
            for candidate in candidates
            if candidate.trust_domain == TrustDomain.STAGING_RECIPE
            and candidate.status == CandidateStatus.SHADOW_ELIGIBLE
        ]
        by_id = {candidate.candidate_id: candidate for candidate in staging}
        history = tuple(
            RecommendationMemoryEntry(
                recommendation_id=f"legacy-{candidate_id}",
                owner_user_id="",
                candidate_id=candidate_id,
                dish=by_id[candidate_id].title if candidate_id in by_id else candidate_id,
                source_type=CandidateSourceType.STAGING_EXTERNAL,
                shown_at=datetime.now(timezone.utc),
            )
            for candidate_id in recent_candidate_ids
        )
        profile = self._legacy_profile(staging, preference_scores or {})
        ranked = self._ranker.rank(
            staging,
            context=RecommendationContext(
                constraints=constraints,
                recent_recommendations=history,
            ),
            preference_profile=profile,
        )
        return [
            RankedRecipeCandidate(
                candidate=item.candidate,
                score=item.score,
                public_trace=self._legacy_public_trace(item.candidate),
            )
            for item in ranked
        ]

    @staticmethod
    def _legacy_profile(
        candidates: Sequence[RecipeCandidate], preference_scores: Mapping[str, float]
    ) -> UserPreferenceProfile:
        now = datetime.now(timezone.utc)
        evidence = tuple(
            PreferenceEvidence(
                dimension=PreferenceDimension.DISH,
                value=candidate.title,
                affinity=max(-1.0, min(1.0, float(preference_scores[candidate.candidate_id]))),
                confidence=1.0,
                source=PreferenceSource.INTERACTION,
                updated_at=now,
                evidence_count=1,
            )
            for candidate in candidates
            if candidate.candidate_id in preference_scores
        )
        return UserPreferenceProfile(
            owner_user_id="",
            policy_version="PREFERENCE_WEIGHT_POLICY_V1",
            evidence=evidence,
            insufficient_evidence=not evidence,
        )

    @staticmethod
    def _legacy_public_trace(candidate: RecipeCandidate) -> tuple[str, ...]:
        # Existing N3 callers expect fixed public strings. N3.2 additionally
        # exposes structured reason codes via ``RankedRecommendation``.
        if candidate.source.source_id == "LOCAL_CANONICAL_CATALOG":
            source = "Món trong thư viện"
        elif candidate.source.source_type in {"CURATED_EXTERNAL", "WEB_SEARCH"}:
            source = "Công thức mới từ nguồn bên ngoài"
        else:
            source = "Công thức đã được tính lại"
        return (
            source,
            "Đã kiểm tra thành phần",
            "Đã tính lại dinh dưỡng từ nguyên liệu",
            "Đang đánh giá công thức ở chế độ thử nghiệm",
        )


__all__ = ["AdaptiveRecommendationPipeline", "RankedRecipeCandidate"]
