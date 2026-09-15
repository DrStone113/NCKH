from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from db.database import get_db
import modules.plans.router as plans_router
from services.agent.planner import PlannerError
from services.agent.tool_registry import ToolRegistry
from services.agent.tools import register_server_tools
from services.auth import AuthenticatedPrincipal, require_authenticated_principal


class _InputUnavailablePlanner:
    async def createLongTermPlan(self, *args, **kwargs):
        raise PlannerError("INPUT_UNAVAILABLE")


async def _unused_db():
    yield None


def test_create_plan_returns_structured_profile_error_with_cors_headers(monkeypatch):
    monkeypatch.setattr(
        plans_router,
        "_legacy_rest_planner",
        lambda db: _InputUnavailablePlanner(),
    )
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(plans_router.router)
    app.dependency_overrides[get_db] = _unused_db
    app.dependency_overrides[require_authenticated_principal] = lambda: AuthenticatedPrincipal("owner")

    with TestClient(app) as client:
        response = client.post(
            "/plans",
            headers={"Origin": "http://localhost:3000"},
            json={
                "user_id": "owner",
                "user_context": {
                    "age": 29,
                    "gender": "male",
                    "equation_sex": None,
                    "height": 170,
                    "weight": 70,
                    "activity_level": "light",
                    "health_goal": "maintain",
                },
                "duration": {"days": 7},
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "INPUT_UNAVAILABLE",
        "message": "Cần bổ sung thông tin ước tính năng lượng trước khi tạo kế hoạch.",
    }
    assert response.headers["access-control-allow-origin"] == "*"


def test_legacy_rest_planner_has_private_write_tools_only():
    planner = plans_router._legacy_rest_planner(object())
    for name in (
        "calculate_tdee",
        "create_plan",
        "suggest_dish",
        "suggest_workout",
        "append_plan_items",
    ):
        assert callable(getattr(planner.tools, name))

    public_registry = ToolRegistry()
    register_server_tools(public_registry)
    assert {"create_plan", "append_plan_items"}.isdisjoint(public_registry.names())
