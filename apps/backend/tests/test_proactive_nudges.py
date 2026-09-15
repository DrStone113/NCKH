"""Tests for the proactive check-in engine.

The engine used to return one of four hardcoded strings based on the clock
alone. These tests pin down the properties that make the new one worth having:
it reads the user's actual day, it stays quiet when there is nothing to say,
and it does not repeat itself.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from models.schemas import CheckinRespondRequest, UserContext
from services.proactive_service import ProactiveService, resolve_time_slot


def at(hour: int) -> datetime:
    return datetime(2026, 7, 26, hour, 0)


# --------------------------------------------------------------------------- #
# Time slots
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "hour,expected",
    [(6, "morning"), (10, "morning"), (12, "lunch"),
     (15, "afternoon"), (20, "evening"), (2, "evening")],
)
def test_resolve_time_slot(hour, expected):
    assert resolve_time_slot(hour) == expected


# --------------------------------------------------------------------------- #
# Knowing when to stay quiet
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_returns_none_when_proactive_disabled():
    svc = ProactiveService()
    svc.get_user_settings("u").enable_proactive = False
    assert await svc.generate_active_nudge("u", UserContext(), now=at(20)) is None


@pytest.mark.asyncio
async def test_returns_none_when_every_category_is_off():
    """Silence is a valid output. The old engine could never produce it."""
    svc = ProactiveService()
    s = svc.get_user_settings("u")
    s.water_checkin = s.nutrition_checkin = False
    s.fitness_checkin = s.mood_checkin = False
    assert await svc.generate_active_nudge("u", UserContext(), now=at(20)) is None


# --------------------------------------------------------------------------- #
# Reading the user's actual day
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_empty_food_log_by_evening_prompts_logging():
    svc = ProactiveService()
    ctx = UserContext(today_meals_count=0, today_exercises_count=2)
    nudge = await svc.generate_active_nudge("u", ctx, now=at(20))
    assert nudge is not None
    assert nudge.category == "nutrition"


@pytest.mark.asyncio
async def test_severe_under_eating_outranks_a_missed_workout():
    """Eating 800 kcal all day matters more than not having exercised."""
    svc = ProactiveService()
    ctx = UserContext(
        age=25, gender="male", equation_sex="male", height=175, weight=70,
        today_meals_count=2, today_calories_consumed=800,
        today_exercises_count=0,
    )
    nudge = await svc.generate_active_nudge("u", ctx, now=at(19))
    assert nudge is not None
    assert nudge.category == "nutrition"
    assert "800" in nudge.message


@pytest.mark.asyncio
async def test_over_eating_is_reported_without_shaming():
    svc = ProactiveService()
    ctx = UserContext(
        age=25, gender="male", equation_sex="male", height=175, weight=70,
        today_meals_count=4, today_calories_consumed=4000,
        today_exercises_count=1,
    )
    nudge = await svc.generate_active_nudge("u", ctx, now=at(19))
    assert nudge is not None
    assert "vượt mục tiêu" in nudge.message
    # Tone check: a calorie overshoot must not be framed as a failure.
    assert "không sao" in nudge.message


@pytest.mark.asyncio
async def test_nudge_does_not_repeat_the_previous_topic():
    svc = ProactiveService()
    ctx = UserContext(today_meals_count=0, today_exercises_count=0)
    first = await svc.generate_active_nudge("u", ctx, now=at(20))
    second = await svc.generate_active_nudge("u", ctx, now=at(20))
    assert first is not None and second is not None
    assert first.category != second.category


@pytest.mark.asyncio
async def test_wording_is_stable_within_a_day():
    """Refreshing the screen must not reshuffle the text under the user."""
    ctx = UserContext(today_meals_count=0)
    a = await ProactiveService().generate_active_nudge("u", ctx, now=at(20))
    b = await ProactiveService().generate_active_nudge("u", ctx, now=at(20))
    assert a.message == b.message


# --------------------------------------------------------------------------- #
# LLM personalisation is best-effort
# --------------------------------------------------------------------------- #

class _StubLLM:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    async def chat(self, messages, tools=None, stream=False):
        self.calls += 1
        return type("R", (), {"full_text": self.text})()


@pytest.mark.asyncio
async def test_llm_rewrites_the_template_when_available():
    llm = _StubLLM("Bạn chưa ghi bữa nào hôm nay, ghi nhanh giúp mình nhé.")
    svc = ProactiveService(llm_client=llm)
    nudge = await svc.generate_active_nudge(
        "u", UserContext(today_meals_count=0), now=at(20)
    )
    assert llm.calls == 1
    assert nudge.message == llm.text


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_the_template():
    class Broken:
        async def chat(self, *args, **kwargs):
            raise RuntimeError("model down")

    nudge = await ProactiveService(llm_client=Broken()).generate_active_nudge(
        "u", UserContext(today_meals_count=0), now=at(20)
    )
    assert nudge is not None and len(nudge.message) > 10


@pytest.mark.asyncio
async def test_slow_llm_times_out_and_falls_back_to_template():
    import asyncio
    import time

    class Slow:
        async def chat(self, *args, **kwargs):
            await asyncio.sleep(30)

    started = time.monotonic()
    nudge = await ProactiveService(llm_client=Slow()).generate_active_nudge(
        "u", UserContext(today_meals_count=0), now=at(20)
    )
    assert time.monotonic() - started < 3.0
    assert nudge is not None and len(nudge.message) > 10


@pytest.mark.asyncio
async def test_runaway_llm_output_is_rejected():
    """A notification must stay a notification."""
    llm = _StubLLM("x" * 400)
    nudge = await ProactiveService(llm_client=llm).generate_active_nudge(
        "u", UserContext(today_meals_count=0), now=at(20)
    )
    assert nudge.message != llm.text


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "option,expected_ml",
    [("opt_water_250", 250), ("opt_water_500", 500), ("opt_water_reached", 2000)],
)
async def test_water_options_log_the_right_amount(option, expected_ml):
    result = await ProactiveService().process_response(
        CheckinRespondRequest(nudge_id="n", selected_option_id=option)
    )
    assert result.logged_data == {"water_ml": expected_ml}


@pytest.mark.asyncio
async def test_tired_answer_gets_a_supportive_reply():
    result = await ProactiveService().process_response(
        CheckinRespondRequest(nudge_id="n", selected_option_id="opt_mood_tired")
    )
    assert result.logged_data == {"mood_score": 2}
    assert "mệt" in result.ai_reply.lower()


@pytest.mark.asyncio
async def test_dismissal_is_accepted_gracefully():
    result = await ProactiveService().process_response(
        CheckinRespondRequest(nudge_id="n", selected_option_id="opt_skip")
    )
    assert result.action_taken == "dismissed"


@pytest.mark.asyncio
async def test_free_text_is_never_echoed_back():
    """The old implementation replied by quoting the user back at themselves."""
    text = "hôm nay mình mệt quá"
    result = await ProactiveService().process_response(
        CheckinRespondRequest(nudge_id="n", response_text=text)
    )
    assert text not in result.ai_reply
