"""
Wger detail endpoints — fetch chi tiết exercise/ingredient từ wger API
"""
import logging
import re
import json
from collections import OrderedDict
from contextlib import asynccontextmanager
from html import unescape

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wger", tags=["wger"])

WGER_BASE = settings.wger_base_url
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
_shared_http_client: httpx.AsyncClient | None = None
_shared_public_cache = None


def configure_http_runtime(client: httpx.AsyncClient, public_cache=None) -> None:
    """Attach the lifespan-owned pool and public-only single-flight cache."""

    global _shared_http_client, _shared_public_cache
    _shared_http_client = client
    _shared_public_cache = public_cache


class _PublicClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get(self, url: str, *, params=None, **kwargs):
        async def _load():
            return await self._client.get(url, params=params, **kwargs)

        if _shared_public_cache is None:
            return await _load()
        key = json.dumps(
            [url, sorted((str(k), str(v)) for k, v in (params or {}).items())],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return await _shared_public_cache.get_or_load(key, _load)


@asynccontextmanager
async def _public_client():
    if _shared_http_client is not None:
        yield _PublicClient(_shared_http_client)
        return
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        yield _PublicClient(client)


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
    aliases: list[str] = Field(default_factory=list)


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
    weight_units: list[WeightUnit] = Field(default_factory=list)
    image_url: str | None = None


class IngredientSearchItem(BaseModel):
    id: int
    name: str
    energy: float | None = None
    protein: float | None = None
    carbohydrates: float | None = None
    fat: float | None = None


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
    text = unescape(text).replace("\xa0", " ")
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _main_image_url(images: object) -> str | None:
    if not isinstance(images, list):
        return None
    valid = [image for image in images if isinstance(image, dict)]
    selected = next((image for image in valid if image.get("is_main") is True), None)
    selected = selected or (valid[0] if valid else None)
    url = selected.get("image") if selected else None
    return str(url) if url else None


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/exercise/{exercise_id}", response_model=ExerciseDetail)
async def get_exercise_detail(exercise_id: int):
    """Fetch chi tiết bài tập từ wger /exerciseinfo/{id}/"""
    url = f"{WGER_BASE}/exerciseinfo/{exercise_id}/?format=json"

    async with _public_client() as client:
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
            image_url = _main_image_url(data.get("images"))

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


@router.get("/ingredient/")
async def search_ingredients(
    name: str = Query(default="", min_length=0, max_length=120),
    page: int = Query(default=1, ge=1),
    language: int = Query(default=2, ge=1),
):
    """Proxy Wger ingredient search with the shape expected by Flutter."""

    params = {"format": "json", "page": page, "language": language}
    if name.strip():
        params["name"] = name.strip()
    async with _public_client() as client:
        try:
            response = await client.get(f"{WGER_BASE}/ingredient/", params=params)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Wger ingredient search unavailable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Wger API error: {response.status_code}")
    data = response.json()
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    results = []
    for raw in raw_results:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        try:
            results.append(IngredientSearchItem.model_validate(raw).model_dump())
        except ValueError:
            continue
    return {
        "count": int(data.get("count", len(results))),
        "next": data.get("next"),
        "results": results,
    }


@router.get("/ingredient/{ingredient_id}", response_model=IngredientDetail)
async def get_ingredient_detail(ingredient_id: int):
    """Fetch chi tiết thực phẩm từ wger /ingredientinfo/{id}/"""
    url = f"{WGER_BASE}/ingredientinfo/{ingredient_id}/?format=json"

    async with _public_client() as client:
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
async def search_exercise(
    name: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=5, ge=1, le=25),
):
    """Tìm kiếm bài tập theo tên từ wger"""
    url = f"{WGER_BASE}/exercise/search/"

    async with _public_client() as client:
        try:
            resp = await client.get(
                url,
                params={"term": name, "language": "english", "format": "json"},
            )
            if resp.status_code != 200:
                return {"suggestions": []}
            data = resp.json()
            return {"suggestions": data.get("suggestions", [])[:limit]}
        except Exception as e:
            logger.warning(f"Exercise search failed: {e}")
            return {"suggestions": []}


@router.get("/exercises", response_model=dict)
async def list_exercises(
    page: int = Query(default=1, ge=1),
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
    
    async with _public_client() as client:
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")
            
            data = resp.json()

            # Extract tên và mô tả từ translations cho mỗi bài tập
            results = []
            for item in data.get("results", []):
                translations = item.get("translations", [])
                # Ưu tiên tiếng Anh (language=2), fallback sang bản đầu tiên
                en_trans = next((t for t in translations if t.get("language") == 2), None)
                trans = en_trans or (translations[0] if translations else {})

                name = trans.get("name", "").strip()
                description = _strip_html(trans.get("description", ""))

                # Bỏ qua bài tập không có tên
                if not name:
                    continue

                # Category
                category_data = item.get("category", {})
                category_name = category_data.get("name", "") if isinstance(category_data, dict) else ""

                # Muscles
                muscles_list = [
                    {
                        "id": m["id"],
                        "name_en": m.get("name_en", m.get("name", "")),
                        "is_front": m.get("is_front", True),
                        "image_url_main": m.get("image_url_main"),
                        "image_url_secondary": m.get("image_url_secondary"),
                    }
                    for m in item.get("muscles", [])
                ]
                muscles_secondary_list = [
                    {
                        "id": m["id"],
                        "name_en": m.get("name_en", m.get("name", "")),
                        "is_front": m.get("is_front", True),
                        "image_url_main": m.get("image_url_main"),
                        "image_url_secondary": m.get("image_url_secondary"),
                    }
                    for m in item.get("muscles_secondary", [])
                ]

                # Equipment
                equipment_list = [
                    {"id": e["id"], "name": e.get("name", "")}
                    for e in item.get("equipment", [])
                ]

                # Image
                image_url = _main_image_url(item.get("images"))

                results.append({
                    "id": item["id"],
                    "name": name,
                    "description": description,
                    "category": category_name,
                    "category_name": category_name,
                    "muscles": muscles_list,
                    "muscles_secondary": muscles_secondary_list,
                    "equipment": equipment_list,
                    "image_url": image_url,
                })

            return {
                "count": data.get("count", 0),
                "next": data.get("next"),  # giữ nguyên để Flutter biết còn trang
                "previous": data.get("previous"),
                "results": results,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching exercises: {e}")
            raise HTTPException(status_code=502, detail=str(e))


@router.get("/categories", response_model=dict)
async def list_categories():
    """Proxy endpoint để lấy danh mục bài tập từ wger"""
    url = f"{WGER_BASE}/exercisecategory/?format=json"
    
    async with _public_client() as client:
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
    
    async with _public_client() as client:
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


@router.get("/equipment/", response_model=dict)
async def list_equipment():
    """Proxy endpoint để lấy danh sách dụng cụ tập từ wger"""
    url = f"{WGER_BASE}/equipment/?format=json"
    
    async with _public_client() as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Wger API error: {resp.status_code}")
            
            return resp.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching equipment: {e}")
            raise HTTPException(status_code=502, detail=str(e))


# ─── SVG Proxy — giải quyết CORS khi Flutter Web fetch SVG từ wger.de ────────

# Whitelist path patterns được phép proxy
_SVG_ALLOWED = re.compile(
    r'^/static/images/muscles/(muscular_system_(front|back)\.svg'
    r'|main/muscle-\d+\.[a-f0-9]+\.svg'
    r'|secondary/muscle-\d+\.[a-f0-9]+\.svg)$'
)

# Cache LRU có giới hạn để proxy lâu ngày không tăng RAM vô hạn.
_svg_cache: OrderedDict[str, bytes] = OrderedDict()
_img_cache: OrderedDict[str, bytes] = OrderedDict()
_SVG_CACHE_LIMIT = 128
_IMG_CACHE_LIMIT = 96


def _cache_get(cache: OrderedDict[str, bytes], key: str) -> bytes | None:
    value = cache.get(key)
    if value is not None:
        cache.move_to_end(key)
    return value


def _cache_put(
    cache: OrderedDict[str, bytes], key: str, value: bytes, limit: int
) -> None:
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


@router.get("/svg")
async def proxy_wger_svg(path: str):
    """
    Proxy SVG từ wger.de để tránh CORS trên Flutter Web.
    Chỉ cho phép path thuộc /static/images/muscles/*.
    
    Ví dụ: GET /wger/svg?path=/static/images/muscles/main/muscle-4.c9fa9a228bc8.svg
    """
    # Validate path — chỉ cho phép SVG nhóm cơ
    if not _SVG_ALLOWED.match(path):
        raise HTTPException(status_code=400, detail="Invalid SVG path")

    # Trả từ cache nếu có
    cached = _cache_get(_svg_cache, path)
    if cached is not None:
        return Response(
            content=cached,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    url = f"https://wger.de{path}"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0),
            headers={"User-Agent": "HealthApp/1.0"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"wger SVG error: {resp.status_code}")

        content = resp.content
        content_type = resp.headers.get("content-type", "").lower()
        if "svg" not in content_type or len(content) > 1_000_000:
            raise HTTPException(status_code=502, detail="Invalid wger SVG response")
        _cache_put(_svg_cache, path, content, _SVG_CACHE_LIMIT)

        return Response(
            content=content,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="wger SVG timeout")
    except Exception as e:
        logger.error("SVG proxy error for %s: %s", path, e)
        raise HTTPException(status_code=502, detail=str(e))

# ─── Image Proxy — exercise images từ wger.de/media/ ────────────────────────

# Whitelist: chỉ cho phép /media/exercise-images/
_IMG_ALLOWED = re.compile(r'^/media/exercise-images/\d+/[\w\-\.]+\.(jpg|jpeg|png|webp)$', re.IGNORECASE)

_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


@router.get("/img")
async def proxy_wger_image(path: str):
    """
    Proxy ảnh bài tập từ wger.de để tránh CORS trên Flutter Web.
    Ví dụ: GET /wger/img?path=/media/exercise-images/957/abc.jpg
    """
    if not _IMG_ALLOWED.match(path):
        raise HTTPException(status_code=400, detail="Invalid image path")

    cached = _cache_get(_img_cache, path)
    if cached is not None:
        ext = path.rsplit(".", 1)[-1].lower()
        return Response(
            content=cached,
            media_type=_MIME.get(ext, "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    url = f"https://wger.de{path}"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=20.0, write=5.0, pool=5.0),
            headers={"User-Agent": "HealthApp/1.0"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"wger image error: {resp.status_code}")

        ext = path.rsplit(".", 1)[-1].lower()
        content = resp.content
        content_type = resp.headers.get("content-type", "").lower()
        if not content_type.startswith("image/") or len(content) > 8_000_000:
            raise HTTPException(status_code=502, detail="Invalid wger image response")
        _cache_put(_img_cache, path, content, _IMG_CACHE_LIMIT)

        return Response(
            content=content,
            media_type=_MIME.get(ext, "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="wger image timeout")
    except Exception as e:
        logger.error("Image proxy error for %s: %s", path, e)
        raise HTTPException(status_code=502, detail=str(e))
