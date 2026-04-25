from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
