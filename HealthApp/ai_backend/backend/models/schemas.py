from typing import Literal
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class UserContext(BaseModel):
    age: int = Field(ge=10, le=120, default=25)
    gender: Literal["male", "female"] = "male"
    height: float = Field(ge=100, le=250, default=170)   # cm
    weight: float = Field(ge=30, le=300, default=70)     # kg
    activity_level: Literal[
        "sedentary", "light", "moderate", "active", "very_active"
    ] = "sedentary"
    health_goal: Literal["lose_weight", "maintain", "gain_muscle"] = "maintain"
    # Today's activity context (optional, sent from Flutter app)
    today_calories_consumed: float | None = None
    today_meals_count: int | None = None
    today_calories_burned: float | None = None
    today_exercises_count: int | None = None
    # Chi tiết bữa ăn và bài tập hôm nay
    today_meals: list[dict] = []
    today_exercises: list[dict] = []

    @field_validator('health_goal', mode='before')
    @classmethod
    def normalize_health_goal(cls, v):
        """Convert short format to full format for backward compatibility"""
        if v == 'lose':
            return 'lose_weight'
        elif v == 'gain':
            return 'gain_muscle'
        return v


class ChatRequest(BaseModel):
    type: Literal["chat"] = "chat"
    session_id: str
    message: str
    user_context: UserContext


class PlanDurationRequest(BaseModel):
    days: int = Field(ge=3, le=120, default=7)


class PlanTarget(BaseModel):
    target_weight: float | None = Field(default=None, ge=30, le=300)
    notes: str | None = None


class CreatePlanRequest(BaseModel):
    user_id: str
    user_context: UserContext
    duration: PlanDurationRequest = PlanDurationRequest()
    target: PlanTarget = PlanTarget()


class PlanItem(BaseModel):
    id: str
    plan_id: str
    day_index: int = Field(ge=1)
    plan_date: date
    item_type: Literal["meal", "exercise"]
    title: str
    payload: dict
    target_kcal: float | None = None
    target_protein: float | None = None
    completed: bool = False


class PlanSummary(BaseModel):
    id: str
    user_id: str
    goal: str
    start_date: date
    end_date: date
    duration_days: int
    daily_kcal_target: float
    daily_protein_target: float | None = None
    status: Literal["active", "completed", "cancelled"]
    created_at: datetime


class PlanDetail(PlanSummary):
    items: list[PlanItem]


class UpdatePlanItemRequest(BaseModel):
    completed: bool


class PlanCheckinRequest(BaseModel):
    user_id: str
    plan_id: str
    weight: float | None = Field(default=None, ge=30, le=300)
    note: str | None = None


class TokenMessage(BaseModel):
    type: Literal["token"] = "token"
    content: str


class WgerMuscle(BaseModel):
    id: int
    name_en: str
    is_front: bool


class WgerEquipmentItem(BaseModel):
    id: int
    name: str


class WgerExerciseData(BaseModel):
    """Dữ liệu bài tập từ wger API / cache"""
    id: int
    name: str
    description: str = ""
    category_id: int | None = None
    category_name: str = ""
    muscles: list[WgerMuscle] = []
    muscles_secondary: list[WgerMuscle] = []
    equipment: list[WgerEquipmentItem] = []
    image_url: str | None = None


class WgerIngredientData(BaseModel):
    """Dữ liệu thực phẩm từ wger API / cache"""
    id: int
    name: str
    energy: float | None = None       # kcal/100g
    protein: float | None = None      # g/100g
    carbohydrates: float | None = None
    fat: float | None = None
    fiber: float | None = None
    sugar: float | None = None


class ActionItem(BaseModel):
    kind: Literal["exercise", "food"]
    wger_id: int
    name: str
    details: dict


class StructuredResponse(BaseModel):
    type: Literal["structured"] = "structured"
    text: str
    meal_name: str | None = None   # tên món ăn khi gợi ý dinh dưỡng
    actions: list[ActionItem]


class DoneMessage(BaseModel):
    type: Literal["done"] = "done"
    full_response: str
    structured: StructuredResponse | None = None


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class KnowledgeChunk(BaseModel):
    id: str
    category: str
    title: str
    content: str
    metadata: dict
    similarity: float


# ---------------------------------------------------------------------------
# Chatbot redesign — domain types (design.md §6.1)
# ---------------------------------------------------------------------------
#
# Các Pydantic class dưới đây phản ánh §6.1 của design document chatbot redesign.
# Chúng tách biệt với `UserContext`, `PlanSummary`, `PlanDetail` ở trên (vẫn
# được giữ lại để không phá API/router hiện tại) và là domain model mới được
# `AgentOrchestrator`, `PlannerAgent`, `Tools.*` sử dụng.


GenderLiteral = Literal["male", "female"]
ActivityLevelLiteral = Literal[
    "sedentary", "light", "moderate", "active", "very_active"
]
HealthGoalLiteral = Literal["lose_weight", "maintain", "gain_muscle"]
MealTypeLiteral = Literal["breakfast", "lunch", "dinner", "snack"]
PlanStatusLiteral = Literal["active", "completed", "cancelled"]
ItemTypeLiteral = Literal["meal", "exercise"]
ChatRoleLiteral = Literal["user", "assistant", "tool"]


class UserProfile(BaseModel):
    """Profile của user — dùng bởi tool `get_user_profile` và planner.

    Field constraints khớp design.md §6.1:
      - age ∈ [10, 120]
      - height_cm ∈ [100, 250]
      - weight_kg ∈ [30, 300]
      - các enum gender / activity_level / health_goal
    """

    user_id: str
    age: int = Field(ge=10, le=120)
    gender: GenderLiteral
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=300)
    activity_level: ActivityLevelLiteral
    health_goal: HealthGoalLiteral
    dietary_restrictions: list[str] = Field(default_factory=list)


class FoodComponent(BaseModel):
    """Một thành phần trong một bữa ăn / một payload meal plan."""

    name: str
    serving_grams: int = Field(ge=1)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float = Field(ge=0)
    fat: float = Field(ge=0)


class Meal(BaseModel):
    id: str
    user_id: str
    meal_date: date
    meal_type: MealTypeLiteral
    dish_name: str
    components: list[FoodComponent]
    total_calories: float = Field(ge=0)
    total_protein: float = Field(ge=0)
    total_carbs: float = Field(ge=0)
    total_fat: float = Field(ge=0)
    logged_at: datetime


class Exercise(BaseModel):
    id: str
    user_id: str
    exercise_date: date
    name: str
    category: str
    duration_minutes: int = Field(ge=0)
    calories_burned: float = Field(ge=0)
    sets: int | None = None
    reps: str | None = None
    logged_at: datetime


class WeightEntry(BaseModel):
    user_id: str
    measured_on: date
    weight_kg: float = Field(ge=30, le=300)


class Plan(BaseModel):
    """Domain Plan record (khác với `PlanSummary` / `PlanDetail` ở trên).

    Validation rules:
      - duration_days ∈ [3, 120]
      - daily_kcal_target > 0
      - daily_protein_target > 0
      - end_date - start_date + 1 == duration_days
    """

    id: str
    user_id: str
    goal: str
    start_date: date
    end_date: date
    duration_days: int = Field(ge=3, le=120)
    daily_kcal_target: float = Field(gt=0)
    daily_protein_target: float = Field(gt=0)
    status: PlanStatusLiteral
    created_at: datetime

    @model_validator(mode="after")
    def _check_duration_matches_dates(self) -> "Plan":
        delta_days = (self.end_date - self.start_date).days + 1
        if delta_days != self.duration_days:
            raise ValueError(
                "Plan.end_date - Plan.start_date + 1 must equal duration_days "
                f"(got {delta_days} days vs duration_days={self.duration_days})"
            )
        return self


class ExerciseItem(BaseModel):
    """Một bài tập trong `ExercisePlanPayload`."""

    name: str
    category: str
    duration_minutes: int = Field(ge=0)
    sets: int = Field(ge=0)
    reps: str
    calories_burned: float = Field(ge=0)


class MealPlanPayload(BaseModel):
    """Payload của PlanItem khi `item_type = "meal"`.

    Validation rules:
      - len(components) >= 1
      - |total_calories - sum(components[i].calories)| <= 1.0
    """

    meal_type: MealTypeLiteral
    dish_name: str
    components: list[FoodComponent] = Field(min_length=1)
    total_calories: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_total_calories_matches_components(self) -> "MealPlanPayload":
        # `min_length=1` đã từ chối list rỗng ở mức Field; bảo vệ thêm ở runtime.
        if len(self.components) < 1:
            raise ValueError("MealPlanPayload.components must contain at least 1 item")
        components_sum = sum(c.calories for c in self.components)
        if abs(self.total_calories - components_sum) > 1.0:
            raise ValueError(
                "MealPlanPayload.total_calories must equal sum(components.calories) "
                f"within ±1.0 kcal (got total={self.total_calories}, "
                f"sum={components_sum}, diff={abs(self.total_calories - components_sum)})"
            )
        return self


class ExercisePlanPayload(BaseModel):
    """Payload của PlanItem khi `item_type = "exercise"`."""

    workout_title: str
    exercises: list[ExerciseItem] = Field(min_length=1)
    total_duration_minutes: int = Field(ge=0)
    total_calories_burned: float = Field(ge=0)


class ChatTurn(BaseModel):
    """Một turn trong `chat_messages` (design.md §6.1)."""

    id: str
    session_id: str
    role: ChatRoleLiteral
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Pinned facts về user (design.md §4.5, §10 — bảng `user_facts`)
# ---------------------------------------------------------------------------

FactCategoryLiteral = Literal[
    "preference", "allergy", "goal", "constraint", "other"
]
FactStatusLiteral = Literal["pending", "confirmed", "rejected"]


class Fact(BaseModel):
    """Một dòng pinned fact đọc từ bảng ``user_facts``.

    Fact được moderate qua ``status`` (``pending`` → ``confirmed`` / ``rejected``).
    Chỉ fact có ``status='confirmed'`` mới được dùng để build System_Prompt
    (Requirement 5.4).
    """

    id: str
    user_id: str
    category: FactCategoryLiteral
    fact: str
    status: FactStatusLiteral
    source_msg_id: str | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Proactive Engagement & Smart Check-in Schemas
# ---------------------------------------------------------------------------

class CheckinQuickOption(BaseModel):
    id: str
    label: str
    icon: str | None = None
    action_type: str  # e.g., 'water_2000ml', 'water_1000ml', 'meal_veggies_yes', 'exercise_done', 'chat'
    value: dict | None = None


class ProactiveNudgeResponse(BaseModel):
    id: str
    category: Literal["hydration", "nutrition", "fitness", "mental"]
    title: str
    message: str
    time_slot: Literal["morning", "lunch", "afternoon", "evening"]
    quick_options: list[CheckinQuickOption] = []
    suggested_action: str | None = None
    created_at: str | None = None


class CheckinRespondRequest(BaseModel):
    nudge_id: str
    user_id: str = "default_user"
    selected_option_id: str | None = None
    response_text: str | None = None
    user_context: UserContext | None = None


class CheckinRespondResult(BaseModel):
    status: str
    ai_reply: str
    action_taken: str | None = None
    logged_data: dict | None = None


class CheckinSettings(BaseModel):
    enable_proactive: bool = True
    water_checkin: bool = True
    nutrition_checkin: bool = True
    fitness_checkin: bool = True
    mood_checkin: bool = True
    preferred_times: list[str] = ["08:30", "12:30", "16:00", "20:00"]

