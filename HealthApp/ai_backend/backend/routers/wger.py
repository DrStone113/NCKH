"""
Wger detail endpoints — fetch chi tiết exercise/ingredient từ wger API
"""
import logging
import re
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wger", tags=["wger"])

WGER_BASE = settings.wger_base_url
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)


# ─── Schemas ────────────────────────────────────────────────────────────────

class MuscleDetail(BaseModel):
    id: int
    name: str
    name_en: str
    is_front: bool
    image_url_main: str | None = None
    image_url_secondary: str | None = None


class ExerciseDetail(BaseModel):
    id: int
    name: str
    description: str
    category: str
    muscles: list[MuscleDetail]
    muscles_secondary: list[MuscleDetail]
    equipment: list[str]
    image_url: str | None = None
    aliases: list[str] = []


class WeightUnit(BaseModel):
    id: int
    gram: float
    name: str


class IngredientDetail(BaseModel):
    id: int
    name: str
    common_name: str | None = None
    brand: str | None = None
    energy: float | None = None
    protein: float | None = None
    carbohydrates: float | None = None
    carbohydrates_sugar: float | None = None
    fat: float | None = None
    fat_saturated: float | None = None
    fiber: float | None = None
    sodium: float | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    nutriscore: str | None = None
    weight_units: list[WeightUnit] = []
    image_url: str | None = None


# ─── Helpers ────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Xóa HTML tags, giữ lại text thuần, format đẹp"""
    if not text:
        return ""
    # Replace block tags with newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|li|div|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<ol[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<ul[^>]*>', '', text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/exercise/{exercise_id}", response_model=ExerciseDetail)
async def get_exercise_detail(exercise_id: int):
    """Fetch chi tiết bài tập từ wger /exerciseinfo/{id}/"""
    url = f"{WGER_BASE}/exerciseinfo/{exercise_id}/?format=json"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Exercise not found")
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")

            data = resp.json()

            # Lấy translation tiếng Anh (language=2) hoặc đầu tiên
            translations = data.get("translations", [])
            en_trans = next((t for t in translations if t.get("language") == 2), None)
            trans = en_trans or (translations[0] if translations else {})

            name = trans.get("name", f"Exercise #{exercise_id}")
            description = _strip_html(trans.get("description", ""))

            # Aliases từ translation
            aliases = trans.get("aliases", [])
            alias_names = [a.get("alias", "") for a in aliases if a.get("alias")]

            # Category
            category = data.get("category", {})
            category_name = category.get("name", "") if isinstance(category, dict) else ""

            # Muscles
            muscles = [
                MuscleDetail(
                    id=m["id"],
                    name=m.get("name", ""),
                    name_en=m.get("name_en", ""),
                    is_front=m.get("is_front", True),
                    image_url_main=m.get("image_url_main"),
                    image_url_secondary=m.get("image_url_secondary"),
                )
                for m in data.get("muscles", [])
            ]
            muscles_secondary = [
                MuscleDetail(
                    id=m["id"],
                    name=m.get("name", ""),
                    name_en=m.get("name_en", ""),
                    is_front=m.get("is_front", True),
                    image_url_main=m.get("image_url_main"),
                    image_url_secondary=m.get("image_url_secondary"),
                )
                for m in data.get("muscles_secondary", [])
            ]

            # Equipment
            equipment = [e.get("name", "") for e in data.get("equipment", [])]

            # Image (từ images array)
            images = data.get("images", [])
            image_url = images[0].get("image") if images else None

            return ExerciseDetail(
                id=exercise_id,
                name=name,
                description=description,
                category=category_name,
                muscles=muscles,
                muscles_secondary=muscles_secondary,
                equipment=equipment,
                image_url=image_url,
                aliases=alias_names,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching exercise {exercise_id}: {e}")
            raise HTTPException(status_code=502, detail=str(e))


@router.get("/ingredient/{ingredient_id}", response_model=IngredientDetail)
async def get_ingredient_detail(ingredient_id: int):
    """Fetch chi tiết thực phẩm từ wger /ingredientinfo/{id}/"""
    url = f"{WGER_BASE}/ingredientinfo/{ingredient_id}/?format=json"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Ingredient not found")
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")

            data = resp.json()

            # Weight units
            weight_units = [
                WeightUnit(
                    id=wu["id"],
                    gram=float(wu.get("gram", 0)),
                    name=wu.get("name", ""),
                )
                for wu in data.get("weight_units", [])
            ]

            # Image
            image_url = None
            if data.get("image"):
                image_url = data["image"]
            elif data.get("thumbnails"):
                image_url = data["thumbnails"].get("original")

            def _to_float(val):
                try:
                    return float(val) if val is not None else None
                except (ValueError, TypeError):
                    return None

            return IngredientDetail(
                id=ingredient_id,
                name=data.get("name", f"Ingredient #{ingredient_id}"),
                common_name=data.get("common_name"),
                brand=data.get("brand"),
                energy=_to_float(data.get("energy")),
                protein=_to_float(data.get("protein")),
                carbohydrates=_to_float(data.get("carbohydrates")),
                carbohydrates_sugar=_to_float(data.get("carbohydrates_sugar")),
                fat=_to_float(data.get("fat")),
                fat_saturated=_to_float(data.get("fat_saturated")),
                fiber=_to_float(data.get("fiber")),
                sodium=_to_float(data.get("sodium")),
                is_vegan=data.get("is_vegan"),
                is_vegetarian=data.get("is_vegetarian"),
                nutriscore=data.get("nutriscore"),
                weight_units=weight_units,
                image_url=image_url,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching ingredient {ingredient_id}: {e}")
            raise HTTPException(status_code=502, detail=str(e))


@router.get("/search/exercise")
async def search_exercise(name: str, limit: int = 5):
    """Tìm kiếm bài tập theo tên từ wger"""
    url = f"{WGER_BASE}/exercise/search/?term={name}&language=english&format=json"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"suggestions": []}
            data = resp.json()
            return {"suggestions": data.get("suggestions", [])[:limit]}
        except Exception as e:
            logger.warning(f"Exercise search failed: {e}")
            return {"suggestions": []}


@router.get("/exercises", response_model=dict)
async def list_exercises(
    page: int = 1,
    category: int | None = None,
    muscles: int | None = None,
):
    """Proxy endpoint để lấy danh sách bài tập từ wger (tránh CORS)"""
    params = {
        "format": "json",
        "language": "2",
        "page": str(page),
    }
    
    if category is not None:
        params["category"] = str(category)
    
    if muscles is not None:
        params["muscles"] = str(muscles)
    
    url = f"{WGER_BASE}/exerciseinfo/"
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")
            
            data = resp.json()
            return data
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching exercises: {e}")
            raise HTTPException(status_code=502, detail=str(e))


@router.get("/categories", response_model=dict)
async def list_categories():
    """Proxy endpoint để lấy danh mục bài tập từ wger"""
    url = f"{WGER_BASE}/exercisecategory/?format=json"
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")
            
            return resp.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            raise HTTPException(status_code=502, detail=str(e))


@router.get("/muscles", response_model=dict)
async def list_muscles():
    """Proxy endpoint để lấy danh sách nhóm cơ từ wger"""
    url = f"{WGER_BASE}/muscle/?format=json"
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")
            
            return resp.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching muscles: {e}")
            raise HTTPException(status_code=502, detail=str(e))
