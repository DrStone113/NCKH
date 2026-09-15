from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from config import Settings
from modules.plans.router import get_active_plan
from services.auth import AuthenticatedPrincipal
from services.agent.context_trace import ContextTraceRecorder


class _Mappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _Mappings(self._row)


class _NoPlanDb:
    async def execute(self, *_args, **_kwargs):
        return _Result(None)


class _BrokenDb:
    async def execute(self, *_args, **_kwargs):
        raise RuntimeError("synthetic database failure")


def test_context_trace_is_disabled_in_production_even_when_requested():
    production = Settings(
        app_environment="production",
        development_context_trace=True,
        _env_file=None,
    )
    development = Settings(
        app_environment="development",
        development_context_trace=True,
        _env_file=None,
    )
    assert production.context_trace_enabled is False
    assert development.context_trace_enabled is True


def test_context_trace_records_stale_snapshot_and_redacts_pii(caplog):
    recorder = ContextTraceRecorder(
        "Email person@example.com; token=sk-syntheticsecret12345",
        enabled=True,
    )
    recorder.capture_initial_context(
        {
            "state_manifest": {
                "today.calories_consumed": {
                    "value": 0,
                    "source": "send_time_meal_snapshot",
                    "observed_at": "2026-08-23T01:00:00Z",
                    "status": "STALE",
                },
                "profile.user_id": {
                    "value": "real-user-id",
                    "source": "firestore.users",
                    "observed_at": None,
                    "status": "KNOWN",
                },
            }
        }
    )
    recorder.finish(outcome="COMPLETED")
    with caplog.at_level(logging.INFO, logger="development.context_trace"):
        recorder.emit()

    payload = json.loads(caplog.records[-1].message.removeprefix("CONTEXT_TRACE "))
    assert payload["source_status"]["today.calories_consumed"] == "STALE"
    assert payload["source_values"]["today.calories_consumed"] == 0
    assert "person@example.com" not in payload["user_query"]
    assert "sk-syntheticsecret12345" not in payload["user_query"]
    assert payload["source_values"]["profile.user_id"].startswith("user:")


@pytest.mark.asyncio
async def test_no_active_plan_is_distinct_from_database_failure(monkeypatch):
    import db.db_status as db_status

    monkeypatch.setattr(db_status, "is_db_offline", lambda: False)

    with pytest.raises(HTTPException) as no_plan:
        await get_active_plan(
            "synthetic-user", _NoPlanDb(), AuthenticatedPrincipal("synthetic-user")
        )
    assert no_plan.value.status_code == 404

    with pytest.raises(HTTPException) as read_error:
        await get_active_plan(
            "synthetic-user", _BrokenDb(), AuthenticatedPrincipal("synthetic-user")
        )
    assert read_error.value.status_code == 503


def test_trace_captures_tool_write_error_without_claiming_success():
    recorder = ContextTraceRecorder("save synthetic meal", enabled=True)
    failed = SimpleNamespace(
        ok=False,
        error="PERSISTENCE_ERROR",
        data={"write_status": "ERROR"},
    )
    recorder.capture_tool_call("log_meal", {"dish_name": "synthetic"})
    recorder.capture_tool_result("log_meal", failed)
    assert recorder.trace.tool_results[-1]["ok"] is False
    assert recorder.trace.tool_results[-1]["data"]["write_status"] == "ERROR"
