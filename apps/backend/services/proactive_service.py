"""Proactive check-in engine.

What changed and why
--------------------
The previous version picked one of four hardcoded messages purely from the
clock. Consequences:

- The same four sentences appeared every single day. A nudge that is identical
  on day 30 and day 1 is one the user has already learned to dismiss.
- ``user_context`` was accepted as a parameter and then ignored, and
  ``llm_client`` was stored and never called — so the app asked "hôm nay bạn đã
  uống đủ 2L nước chưa?" while holding the logs that answer it.
- It always returned a nudge. Never having nothing to say is itself a form of
  not paying attention.

This version scores candidate topics against the user's actual day, returns
``None`` when nothing is worth interrupting for, and varies its phrasing so a
daily user does not read the same sentence twice in a row. When an LLM client
is wired in, the chosen topic is rendered into a personalised sentence; the
deterministic templates remain as the fallback so the endpoint keeps working
with no model available.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from models.schemas import (
    CheckinQuickOption,
    CheckinRespondRequest,
    CheckinRespondResult,
    CheckinSettings,
    ProactiveNudgeResponse,
    UserContext,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Time slots
# --------------------------------------------------------------------------- #

def resolve_time_slot(hour: int) -> str:
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 14:
        return "lunch"
    if 14 <= hour < 18:
        return "afternoon"
    return "evening"


# --------------------------------------------------------------------------- #
# Candidate scoring
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class NudgeCandidate:
    """One thing the app could say, plus how much it deserves saying."""

    category: str
    score: float
    title: str
    message: str
    suggested_action: str
    options: list[CheckinQuickOption]


# Below this, staying quiet beats interrupting.
MIN_SCORE_TO_SHOW = 1.0


def _estimate_daily_target(ctx: UserContext) -> float | None:
    """Daily kcal target via the same TDEE maths the chat agent uses.

    Imported lazily and defensively: a nudge is never important enough to
    justify a 500 from a shared calculation module.
    """
    try:
        from services.agent.tools.tdee import calculate_tdee

        # NOTE: ``UserContext`` and ``UserProfile`` disagree on field names —
        # the former uses ``height``/``weight``, the latter ``height_cm``/
        # ``weight_kg`` and additionally requires ``user_id``. Passing the
        # UserContext fields through verbatim fails Pydantic validation, which
        # ``calculate_tdee`` reports as ValueError("INVALID_PROFILE"); the
        # except branch below would then swallow it and silently disable every
        # calorie-aware nudge. Map explicitly.
        result = calculate_tdee({
            "user_id": "nudge",
            "age": ctx.age,
            "gender": ctx.gender,
            "equation_sex": ctx.equation_sex,
            "nutrition_safety_profile": ctx.nutrition_safety_profile.model_dump(
                mode="json"
            ),
            "height_cm": ctx.height,
            "weight_kg": ctx.weight,
            "activity_level": ctx.activity_level,
            "health_goal": ctx.health_goal,
        })
        value = result.get("daily_kcal") or result.get("tdee")
        return float(value) if value else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("TDEE estimate unavailable for nudge: %s", exc)
        return None


def _estimate_approximate_fluid_goal(ctx: UserContext) -> float | None:
    """Return the policy-v1 heuristic in mL, or no goal when unsupported."""
    try:
        from services.agent.tools.tdee import calculate_tdee

        result = calculate_tdee(
            {
                "user_id": "nudge",
                "age": ctx.age,
                "gender": ctx.gender,
                "equation_sex": ctx.equation_sex,
                "nutrition_safety_profile": ctx.nutrition_safety_profile.model_dump(
                    mode="json"
                ),
                "height_cm": ctx.height,
                "weight_kg": ctx.weight,
                "activity_level": ctx.activity_level,
                "health_goal": ctx.health_goal,
            }
        )
        fluid = result.get("fluid")
        if not isinstance(fluid, dict):
            return None
        value = fluid.get("approximate_fluid_goal_ml_per_day")
        return float(value) if value is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Fluid estimate unavailable for nudge: %s", exc)
        return None


class ProactiveService:
    """Chooses what — if anything — to say to the user right now."""

    def __init__(self, llm_client: Any = None) -> None:
        self.llm_client = llm_client
        self._user_settings: dict[str, CheckinSettings] = {}
        # Last nudge category shown per user, so two consecutive check-ins do
        # not land on the same topic.
        self._last_category: dict[str, str] = {}

    # ---------------------------------------------------------------- settings
    def get_user_settings(self, user_id: str) -> CheckinSettings:
        if user_id not in self._user_settings:
            self._user_settings[user_id] = CheckinSettings()
        return self._user_settings[user_id]

    def update_user_settings(self, user_id: str, settings: CheckinSettings) -> CheckinSettings:
        self._user_settings[user_id] = settings
        return settings

    # ------------------------------------------------------------------ nudge
    async def generate_active_nudge(
        self,
        user_id: str,
        user_context: Optional[UserContext] = None,
        now: datetime | None = None,
    ) -> Optional[ProactiveNudgeResponse]:
        """Return the most relevant check-in, or ``None`` to stay quiet."""
        settings = self.get_user_settings(user_id)
        if not settings.enable_proactive:
            return None

        current = now or datetime.now()
        time_slot = resolve_time_slot(current.hour)
        ctx = user_context or UserContext()

        candidates = self._build_candidates(ctx, time_slot, settings, current)
        if not candidates:
            return None

        # Penalise repeating the topic shown last time so consecutive check-ins
        # feel like a conversation rather than a loop.
        last = self._last_category.get(user_id)
        for candidate in candidates:
            if candidate.category == last:
                candidate.score -= 0.75

        best = max(candidates, key=lambda c: c.score)
        if best.score < MIN_SCORE_TO_SHOW:
            logger.debug(
                "Staying quiet for user=%s (best score %.2f)", user_id, best.score
            )
            return None

        message = await self._personalise(best, ctx, time_slot)
        self._last_category[user_id] = best.category

        return ProactiveNudgeResponse(
            id=f"nudge_{user_id}_{best.category}_{current.strftime('%Y%m%d%H')}",
            category=best.category,
            title=best.title,
            message=message,
            time_slot=time_slot,
            quick_options=best.options,
            suggested_action=best.suggested_action,
            created_at=current.isoformat(),
        )

    # ------------------------------------------------------------- candidates
    def _build_candidates(
        self,
        ctx: UserContext,
        time_slot: str,
        settings: CheckinSettings,
        now: datetime,
    ) -> list[NudgeCandidate]:
        candidates: list[NudgeCandidate] = []
        meals = ctx.today_meals_count or 0
        exercises = ctx.today_exercises_count or 0
        consumed = ctx.today_calories_consumed or 0.0
        target = _estimate_daily_target(ctx)
        fluid_goal_ml = _estimate_approximate_fluid_goal(ctx)

        # Rotate wording by day so the same topic does not read identically
        # two days running. Seeded by date, so it is stable within a day —
        # refreshing the screen must not reshuffle the text.
        rng = random.Random(f"{now.date()}::{time_slot}")

        # --- nutrition ------------------------------------------------------
        if settings.nutrition_checkin:
            if meals == 0 and time_slot in ("lunch", "afternoon", "evening"):
                # Nothing logged well into the day: the most actionable gap.
                candidates.append(NudgeCandidate(
                    category="nutrition",
                    score=3.0 if time_slot != "lunch" else 2.4,
                    title="Nhật ký hôm nay còn trống",
                    message=rng.choice([
                        "Hôm nay bạn chưa ghi bữa nào. Ghi nhanh giúp mình theo dõi được calo và đạm nhé?",
                        "Mình chưa thấy bữa ăn nào của bạn hôm nay. Bạn ăn gì rồi, ghi lại một chút nhé?",
                    ]),
                    suggested_action="Ghi lại bữa gần nhất",
                    options=[
                        CheckinQuickOption(id="opt_log_meal", label="Ghi bữa ăn 📝",
                                           icon="restaurant", action_type="navigate_meal_log"),
                        CheckinQuickOption(id="opt_skip", label="Để sau",
                                           icon="schedule", action_type="dismiss"),
                    ],
                ))
            elif target and consumed and time_slot in ("afternoon", "evening"):
                remaining = target - consumed
                if remaining > 500:
                    # Severe under-eating is a health signal, not a nagging
                    # opportunity — it outranks routine "you haven't exercised"
                    # prompts. Scale with the size of the deficit so a 200 kcal
                    # shortfall and a 1200 kcal one are not treated alike.
                    severity = remaining / target
                    score = 3.4 if severity >= 0.4 else 2.5
                    candidates.append(NudgeCandidate(
                        category="nutrition",
                        score=score,
                        title="Bạn đang ăn khá ít",
                        message=(
                            f"Hôm nay bạn mới nạp khoảng {consumed:.0f} kcal, "
                            f"còn thiếu chừng {remaining:.0f} kcal so với mục tiêu. "
                            "Ăn thiếu nhiều dễ mất cơ chứ không chỉ giảm mỡ đâu."
                        ),
                        suggested_action="Bổ sung một bữa có đạm",
                        options=[
                            CheckinQuickOption(id="opt_suggest_dish", label="Gợi ý món 🍲",
                                               icon="restaurant_menu", action_type="chat"),
                            CheckinQuickOption(id="opt_log_meal", label="Ghi bữa ăn 📝",
                                               icon="edit", action_type="navigate_meal_log"),
                        ],
                    ))
                elif remaining < -300:
                    candidates.append(NudgeCandidate(
                        category="nutrition",
                        score=2.0,
                        title="Đã vượt mục tiêu hôm nay",
                        message=(
                            f"Hôm nay bạn đã nạp khoảng {consumed:.0f} kcal, "
                            f"vượt mục tiêu chừng {abs(remaining):.0f} kcal. "
                            "Một hôm lệch không sao cả — mai cân lại là ổn."
                        ),
                        suggested_action="Đi bộ nhẹ 20 phút",
                        options=[
                            CheckinQuickOption(id="opt_walk", label="Đi bộ 20 phút 🚶",
                                               icon="directions_walk", action_type="exercise_done"),
                            CheckinQuickOption(id="opt_chat", label="Hỏi thêm 💬",
                                               icon="chat", action_type="chat"),
                        ],
                    ))

        # --- fitness --------------------------------------------------------
        if settings.fitness_checkin and time_slot in ("afternoon", "evening"):
            if exercises == 0:
                candidates.append(NudgeCandidate(
                    category="fitness",
                    score=2.3 if time_slot == "evening" else 1.6,
                    title="Hôm nay chưa vận động",
                    message=rng.choice([
                        "Hôm nay bạn chưa ghi buổi tập nào. Mười lăm phút đi bộ hay giãn cơ cũng đã tính rồi đấy.",
                        "Chưa thấy hoạt động nào hôm nay. Vận động nhẹ cuối ngày giúp ngủ ngon hơn hẳn.",
                    ]),
                    suggested_action="Vận động nhẹ 15 phút",
                    options=[
                        CheckinQuickOption(id="opt_workout_suggest", label="Gợi ý bài tập 🏋️",
                                           icon="fitness_center", action_type="chat"),
                        CheckinQuickOption(id="opt_exercise_done", label="Mình tập rồi ✅",
                                           icon="check_circle", action_type="exercise_done"),
                    ],
                ))
            else:
                burned = ctx.today_calories_burned or 0
                candidates.append(NudgeCandidate(
                    category="fitness",
                    score=1.2,
                    title="Ghi nhận hôm nay",
                    message=(
                        f"Bạn đã tập {exercises} buổi hôm nay"
                        + (f", đốt khoảng {burned:.0f} kcal" if burned else "")
                        + ". Giữ nhịp này là được rồi."
                    ),
                    suggested_action="Duy trì nhịp tập",
                    options=[
                        CheckinQuickOption(id="opt_log_more", label="Ghi thêm buổi tập",
                                           icon="add", action_type="navigate_exercise_log"),
                    ],
                ))

        # --- hydration ------------------------------------------------------
        # No water field exists on UserContext yet, so this stays a low-priority
        # offer to log rather than a question the app should already know.
        if settings.water_checkin and time_slot in ("morning", "afternoon"):
            candidates.append(NudgeCandidate(
                category="hydration",
                score=1.1,
                title="Uống nước",
                message=rng.choice([
                    "Tiện tay ghi lại lượng nước đã uống nhé, để mình theo dõi giúp bạn.",
                    "Bạn uống được bao nhiêu nước rồi? Ghi nhanh một chạm thôi.",
                ]),
                suggested_action=(
                    f"Mục tiêu dịch gần đúng khoảng {fluid_goal_ml:.0f} ml/ngày"
                    if fluid_goal_ml is not None
                    else "Ghi lượng nước đã uống"
                ),
                options=[
                    CheckinQuickOption(id="opt_water_250", label="+250ml 💧",
                                       icon="water_drop", action_type="water_log",
                                       value={"water_ml": 250}),
                    CheckinQuickOption(id="opt_water_500", label="+500ml 🌊",
                                       icon="local_drink", action_type="water_log",
                                       value={"water_ml": 500}),
                ],
            ))

        # --- mental ---------------------------------------------------------
        if settings.mood_checkin and time_slot == "evening":
            candidates.append(NudgeCandidate(
                category="mental",
                score=1.4,
                title="Cuối ngày",
                message=rng.choice([
                    "Hôm nay của bạn thế nào? Ngủ và mức căng thẳng cũng ảnh hưởng tới cân nặng đấy.",
                    "Một ngày nữa trôi qua. Bạn thấy trong người ổn chứ?",
                ]),
                suggested_action="Ghi lại tâm trạng và giấc ngủ",
                options=[
                    CheckinQuickOption(id="opt_mood_good", label="Ổn 😊",
                                       icon="sentiment_satisfied", action_type="mood_great"),
                    CheckinQuickOption(id="opt_mood_tired", label="Hơi mệt 😪",
                                       icon="sentiment_dissatisfied", action_type="mood_tired"),
                    CheckinQuickOption(id="opt_chat", label="Nói chuyện 💬",
                                       icon="chat", action_type="chat"),
                ],
            ))

        return candidates

    # ----------------------------------------------------------- personalising
    async def _personalise(
        self, candidate: NudgeCandidate, ctx: UserContext, time_slot: str
    ) -> str:
        """Rewrite the template through the LLM when one is available.

        Falls back to the template on any failure. A check-in is not worth
        blocking on, so the LLM path is strictly best-effort.
        """
        if self.llm_client is None:
            return candidate.message

        goal_vi = {
            "lose_weight": "giảm cân",
            "gain_muscle": "tăng cơ",
            "maintain": "giữ dáng",
        }.get(ctx.health_goal, ctx.health_goal)

        prompt = (
            "Viết lại lời nhắc dưới đây cho ứng dụng sức khỏe, giữ nguyên ý và "
            "số liệu, nhưng nghe tự nhiên như một huấn luyện viên nhắn tin.\n"
            f"Bối cảnh: người dùng mục tiêu {goal_vi}, đang là {time_slot}.\n"
            f"Lời nhắc gốc: {candidate.message}\n\n"
            "Yêu cầu: tối đa 2 câu, không chào hỏi, không emoji, không hỏi lại "
            "thông tin ứng dụng đã có. Chỉ trả về câu đã viết lại."
        )
        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}], tools=None, stream=False
            )
            text = (getattr(response, "full_text", "") or "").strip()
            # Guard against a model that ignores the length limit and turns a
            # notification into an essay.
            if text and len(text) <= 300:
                return text
        except Exception as exc:  # noqa: BLE001 - best effort by design
            logger.debug("Nudge personalisation failed, using template: %s", exc)
        return candidate.message

    # --------------------------------------------------------------- response
    async def process_response(self, req: CheckinRespondRequest) -> CheckinRespondResult:
        """Acknowledge the user's check-in answer."""
        opt_id = (req.selected_option_id or "").lower()
        text = (req.response_text or "").strip()

        # Structured quick-option answers map to a logged action.
        if "water" in opt_id or opt_id.startswith("opt_w_"):
            amount = 250
            if "500" in opt_id:
                amount = 500
            elif "2000" in opt_id or "reached" in opt_id:
                amount = 2000
            return CheckinRespondResult(
                status="success",
                ai_reply=f"Đã ghi {amount}ml. Cứ rải đều trong ngày là tốt nhất.",
                action_taken="water_logged",
                logged_data={"water_ml": amount},
            )

        if "nut" in opt_id or "veggies" in opt_id:
            return CheckinRespondResult(
                status="success",
                ai_reply="Ghi nhận bữa ăn. Bổ sung đủ rau xanh và chất xơ giúp tiêu hóa rất tốt.",
                action_taken="nutrition_logged",
            )

        if "exercise" in opt_id or "workout" in opt_id or "walk" in opt_id:
            return CheckinRespondResult(
                status="success",
                ai_reply="Đã ghi nhận buổi vận động. Đều đặn quan trọng hơn nặng nhẹ.",
                action_taken="exercise_logged",
            )

        if "mood_tired" in opt_id:
            return CheckinRespondResult(
                status="success",
                ai_reply=(
                    "Đã ghi lại. Mệt kéo dài thường kéo theo ăn vặt nhiều hơn — "
                    "nếu mai vẫn vậy thì nhắn mình, xem lại lịch ngủ và lượng ăn nhé."
                ),
                action_taken="mood_logged",
                logged_data={"mood_score": 2},
            )

        if "mood" in opt_id:
            return CheckinRespondResult(
                status="success",
                ai_reply="Ghi lại rồi. Giữ nhịp này nhé.",
                action_taken="mood_logged",
                logged_data={"mood_score": 4},
            )

        if "dismiss" in opt_id or "skip" in opt_id:
            return CheckinRespondResult(
                status="success",
                ai_reply="Được, để lúc khác.",
                action_taken="dismissed",
            )

        # Free-text answers deserve a real reply, not an echo of what the user
        # just typed (which is what this used to do).
        if text and self.llm_client is not None:
            reply = await self._reply_to_free_text(text, req.user_context)
            if reply:
                return CheckinRespondResult(
                    status="success", ai_reply=reply, action_taken="custom_reply"
                )

        return CheckinRespondResult(
            status="success",
            ai_reply="Đã ghi nhận. Bạn cần mình hỗ trợ gì thêm không?",
            action_taken="acknowledged",
        )

    async def _reply_to_free_text(
        self, text: str, ctx: Optional[UserContext]
    ) -> str | None:
        goal = getattr(ctx, "health_goal", "maintain") if ctx else "maintain"
        prompt = (
            "Người dùng vừa trả lời một lời nhắc sức khỏe trong ứng dụng. "
            f"Mục tiêu của họ: {goal}.\n"
            f"Họ nói: \"{text}\"\n\n"
            "Trả lời như một huấn luyện viên: tối đa 2 câu, có ích, không lặp "
            "lại lời họ, không chào hỏi, không emoji. Nếu họ nêu triệu chứng "
            "nghiêm trọng, khuyên đi khám."
        )
        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}], tools=None, stream=False
            )
            reply = (getattr(response, "full_text", "") or "").strip()
            return reply if reply and len(reply) <= 400 else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Free-text check-in reply failed: %s", exc)
            return None


__all__ = ["MIN_SCORE_TO_SHOW", "NudgeCandidate", "ProactiveService", "resolve_time_slot"]
