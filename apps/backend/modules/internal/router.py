"""Aggregate backend-cost telemetry without private request data."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from services.auth import AuthenticatedPrincipal, require_authenticated_principal


router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/backend-cost")
async def get_backend_cost_metrics(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> dict[str, Any]:
    if not principal.is_developer:
        raise HTTPException(status_code=403, detail="DEVELOPER_ROLE_REQUIRED")
    metrics = getattr(request.app.state, "backend_cost_metrics", None)
    if metrics is None:
        raise HTTPException(status_code=503, detail="BACKEND_COST_METRICS_UNAVAILABLE")
    payload = metrics.snapshot()
    payload["mode"] = getattr(request.app.state, "backend_cost_mode", None)
    counters = payload.get("counters", {})

    def rate(numerator: str, denominator_names: tuple[str, ...]) -> float:
        denominator = sum(int(counters.get(name, 0)) for name in denominator_names)
        return round(int(counters.get(numerator, 0)) / denominator, 4) if denominator else 0.0

    payload["rates"] = {
        "deterministic_early_exit": rate(
            "inference.deterministic_early_exit",
            (
                "inference.route.deterministic",
                "inference.route.light_llm",
                "inference.route.heavy_llm",
            ),
        ),
        "prefetch_hit": rate("prefetch.hit", ("prefetch.hit", "prefetch.failure")),
        "lexical_early_exit": rate(
            "retrieval.lexical_exit",
            (
                "retrieval.exact_exit",
                "retrieval.lexical_exit",
                "retrieval.dense_calls",
            ),
        ),
        "private_cache_hit": rate(
            "private_cache.hit", ("private_cache.hit", "private_cache.miss")
        ),
        "validator_failure": rate(
            "validator.failure", ("validator.pass", "validator.failure")
        ),
    }
    payload["policy_version"] = "inference-policy-v2.0.0"
    return payload


__all__ = ["router"]
