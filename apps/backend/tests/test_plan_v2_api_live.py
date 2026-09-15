"""Authenticated live PostgreSQL integration for the Plan V2 HTTP contract."""

from __future__ import annotations

import os
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings
from modules.plans.v2_router import router
from services.plan_engine.engine import GLOBAL_PLAN_REPOSITORY


_LIVE_URL = os.getenv("PLAN_V2_LIVE_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not _LIVE_URL, reason="PLAN_V2_LIVE_POSTGRES_URL is not configured")


def _token(owner: str) -> str:
    return jwt.encode({"sub": owner}, settings.jwt_secret, algorithm="HS256")


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_authenticated_plan_v2_api_is_owner_scoped_and_readback_authoritative():
    owner = f"p2-2-api-{uuid4()}"
    other = f"p2-2-other-{uuid4()}"
    owner_headers = {"Authorization": f"Bearer {_token(owner)}"}
    other_headers = {"Authorization": f"Bearer {_token(other)}"}
    with TestClient(_app()) as client:
        draft = client.post(
            "/api/plan-v2/drafts/nutrition",
            headers=owner_headers,
            json={
                "period_start": "2026-11-12",
                "period_end": "2026-11-12",
                "timezone": "Asia/Ho_Chi_Minh",
                "profile": {
                    "age": 30,
                    "equation_sex": "female",
                    "height_cm": 163,
                    "weight_kg": 58,
                    "activity_level": "light",
                    "health_goal": "maintain",
                },
            },
        )
        assert draft.status_code == 200, draft.text
        preview = draft.json()["plan"]
        assert preview["lifecycle_status"] == "DRAFT"

        # Simulate a backend restart: the save must restore the exact preview
        # from PostgreSQL rather than relying on process memory.
        GLOBAL_PLAN_REPOSITORY._revisions.pop(preview["revision_id"], None)  # noqa: SLF001
        GLOBAL_PLAN_REPOSITORY._by_plan.pop(preview["plan_id"], None)  # noqa: SLF001

        saved = client.post(
            "/api/plan-v2/plans/save",
            headers=owner_headers,
            json={
                "plan_id": preview["plan_id"],
                "revision_id": preview["revision_id"],
                "revision_content_hash": preview["revision_content_hash"],
                "action_id": f"save-{uuid4()}",
            },
        )
        assert saved.status_code == 200, saved.text
        saved_plan = saved.json()["plan"]
        assert saved_plan["lifecycle_status"] == "SAVED"
        assert saved_plan["revision_content_hash"] == preview["revision_content_hash"]

        exact = client.get(
            f"/api/plan-v2/plans/{preview['plan_id']}?revision_id={preview['revision_id']}",
            headers=owner_headers,
        )
        assert exact.status_code == 200
        assert exact.json()["plan"]["revision_id"] == preview["revision_id"]
        assert client.get(
            f"/api/plan-v2/plans/{preview['plan_id']}?revision_id={preview['revision_id']}",
            headers=other_headers,
        ).status_code == 404

        active = client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/activate",
            headers=owner_headers,
            json={"expected_revision_number": 1, "action_id": f"activate-{uuid4()}"},
        )
        assert active.status_code == 200, active.text
        assert active.json()["plan"]["lifecycle_status"] == "ACTIVE"
        assert client.get("/api/plan-v2/plans/active/NUTRITION", headers=owner_headers).status_code == 200

        paused = client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/pause",
            headers=owner_headers,
            json={"expected_revision_number": 1, "action_id": f"pause-{uuid4()}"},
        )
        assert paused.status_code == 200, paused.text
        resumed = client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/resume",
            headers=owner_headers,
            json={"expected_revision_number": 1, "action_id": f"resume-{uuid4()}"},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["plan"]["lifecycle_status"] == "ACTIVE"

        # A repeated resume is not silently accepted as a second transition,
        # and an owner mismatch is indistinguishable from a missing plan.
        assert client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/resume",
            headers=owner_headers,
            json={"expected_revision_number": 1, "action_id": f"repeat-resume-{uuid4()}"},
        ).status_code == 409
        assert client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/resume",
            headers=other_headers,
            json={"expected_revision_number": 1, "action_id": f"foreign-resume-{uuid4()}"},
        ).status_code == 404
        assert client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/activate",
            headers=owner_headers,
            json={"expected_revision_number": 99, "action_id": f"stale-activate-{uuid4()}"},
        ).status_code == 409

        cancelled = client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/cancel",
            headers=owner_headers,
            json={"expected_revision_number": 1, "action_id": f"cancel-{uuid4()}"},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["plan"]["lifecycle_status"] == "CANCELLED"
        assert client.post(
            f"/api/plan-v2/plans/{preview['plan_id']}/revisions/{preview['revision_id']}/resume",
            headers=owner_headers,
            json={"expected_revision_number": 1, "action_id": f"cancelled-resume-{uuid4()}"},
        ).status_code == 409


def test_plan_v2_api_rejects_anonymous_calls_before_any_repository_read():
    with TestClient(_app()) as client:
        response = client.get("/api/plan-v2/plans")
    assert response.status_code == 401
    assert response.json()["detail"] == "AUTHENTICATED_PRINCIPAL_REQUIRED"
