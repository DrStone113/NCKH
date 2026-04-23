"""
WgerService — Fetch và cache dữ liệu từ wger.de API

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 8.7
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.schemas import WgerEquipmentItem, WgerExerciseData, WgerIngredientData, WgerMuscle

logger = logging.getLogger(__name__)


class WgerService:
    """Service để fetch và cache dữ liệu từ wger API"""

    def __init__(self):
        self.base_url = settings.wger_base_url
        self.timeout = settings.wger_request_timeout_seconds
        self.cache_ttl_hours = settings.wger_cache_ttl_hours
        self.enabled = settings.wger_enabled

    async def fetch_all_exercises(self, db: AsyncSession) -> list[WgerExerciseData]:
        """
        Fetch tất cả bài tập từ wger API hoặc cache.
        
        Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 8.7
        """
        # Xử lý WGER_ENABLED=false
        if not self.enabled:
            logger.info("WGER_ENABLED=false, returning empty list")
            return []

        # Kiểm tra cache TTL
        if await self._is_cache_valid("exercises", db):
            logger.info("Cache valid, returning exercises from DB")
            return await self._get_exercises_from_cache(db)

        # Fetch từ wger API
        logger.info("Cache invalid or empty, fetching from wger API")
        try:
            raw_data = await self._fetch_paginated("/exerciseinfo/?format=json&language=2")
            exercises = self._parse_exercises(raw_data)
            
            # Save to cache
            await self._save_exercises_to_cache(exercises, db)
            
            return exercises
        except httpx.TimeoutException as e:
            logger.warning(f"Timeout fetching exercises from wger API: {e}")
            raise TimeoutError(f"Wger API timeout after {self.timeout} seconds")

    async def fetch_all_ingredients(self, db: AsyncSession) -> list[WgerIngredientData]:
        """
        Fetch tất cả thực phẩm từ wger API hoặc cache.
        
        Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 8.7
        """
        # Xử lý WGER_ENABLED=false
        if not self.enabled:
            logger.info("WGER_ENABLED=false, returning empty list")
            return []

        # Kiểm tra cache TTL
        if await self._is_cache_valid("ingredients", db):
            logger.info("Cache valid, returning ingredients from DB")
            return await self._get_ingredients_from_cache(db)

        # Fetch từ wger API
        logger.info("Cache invalid or empty, fetching from wger API")
        try:
            raw_data = await self._fetch_paginated("/ingredient/?format=json&language=2")
            ingredients = self._parse_ingredients(raw_data)
            
            # Save to cache
            await self._save_ingredients_to_cache(ingredients, db)
            
            return ingredients
        except httpx.TimeoutException as e:
            logger.warning(f"Timeout fetching ingredients from wger API: {e}")
            raise TimeoutError(f"Wger API timeout after {self.timeout} seconds")

    async def _fetch_paginated(self, endpoint: str) -> list[dict]:
        """
        Fetch tất cả trang từ wger API endpoint có pagination.
        Timeout áp dụng per-request (không phải toàn bộ session) để tránh
        timeout khi ingredient API có nhiều trang.

        Requirements: 1.3, 1.6, 1.7
        """
        results = []
        url = f"{self.base_url}{endpoint}"
        page_num = 0
        # Per-request timeout: đủ lớn cho mỗi trang nhưng không block mãi
        per_request_timeout = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=5.0)

        async with httpx.AsyncClient(timeout=per_request_timeout) as client:
            while url:
                page_num += 1
                try:
                    logger.info(f"Fetching page {page_num} from {url}")
                    response = await client.get(url)

                    if response.status_code != 200:
                        error_msg = f"Wger API error: endpoint={endpoint}, status_code={response.status_code}"
                        logger.error(error_msg)
                        raise Exception(error_msg)

                    data = response.json()
                    page_results = data.get("results", [])
                    results.extend(page_results)
                    url = data.get("next")  # None khi hết trang
                    logger.debug(f"Page {page_num}: got {len(page_results)} items, total={len(results)}")

                except httpx.TimeoutException as e:
                    logger.warning(f"Timeout on page {page_num} of {endpoint}: {e}")
                    raise
                except Exception as e:
                    if "status_code" not in str(e):
                        logger.error(f"Error fetching page {page_num} from {endpoint}: {e}")
                    raise

        logger.info(f"Fetched {len(results)} total items from {endpoint} ({page_num} pages)")
        return results

    async def _is_cache_valid(self, cache_type: str, db: AsyncSession) -> bool:
        """
        Kiểm tra xem cache có còn valid không (dựa trên TTL).
        
        Requirements: 1.5
        """
        table_name = f"wger_{cache_type}"
        
        try:
            # Query MAX(cached_at) từ bảng tương ứng
            query = text(f"SELECT MAX(cached_at) FROM {table_name}")
            result = await db.execute(query)
            max_cached_at = result.scalar()
            
            if max_cached_at is None:
                logger.debug(f"No cache found in {table_name}")
                return False
            
            # So sánh với WGER_CACHE_TTL_HOURS
            now = datetime.now(timezone.utc)
            cache_age = now - max_cached_at.replace(tzinfo=timezone.utc)
            ttl = timedelta(hours=self.cache_ttl_hours)
            
            is_valid = cache_age < ttl
            logger.debug(f"Cache age: {cache_age}, TTL: {ttl}, valid: {is_valid}")
            return is_valid
        
        except Exception as e:
            logger.warning(f"Error checking cache validity: {e}")
            return False

    async def _save_exercises_to_cache(
        self, exercises: list[WgerExerciseData], db: AsyncSession
    ) -> None:
        """
        Upsert exercises vào wger_exercises cache table.
        
        Requirements: 1.4
        """
        if not exercises:
            return
        
        logger.info(f"Saving {len(exercises)} exercises to cache")
        
        for exercise in exercises:
            # Serialize JSONB fields as strings, cast via CAST() to avoid asyncpg named-param conflict
            muscles_json = json.dumps([m.model_dump() for m in exercise.muscles])
            muscles_secondary_json = json.dumps([m.model_dump() for m in exercise.muscles_secondary])
            equipment_json = json.dumps([e.model_dump() for e in exercise.equipment])
            
            # Use CAST(:param AS jsonb) instead of :param::jsonb — asyncpg doesn't support :: in named params
            query = text("""
                INSERT INTO wger_exercises 
                    (id, name, description, category_id, category_name, 
                     muscles, muscles_secondary, equipment, image_url, cached_at)
                VALUES 
                    (:id, :name, :description, :category_id, :category_name,
                     CAST(:muscles AS jsonb), CAST(:muscles_secondary AS jsonb),
                     CAST(:equipment AS jsonb), :image_url, :cached_at)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    category_id = EXCLUDED.category_id,
                    category_name = EXCLUDED.category_name,
                    muscles = EXCLUDED.muscles,
                    muscles_secondary = EXCLUDED.muscles_secondary,
                    equipment = EXCLUDED.equipment,
                    image_url = EXCLUDED.image_url,
                    cached_at = EXCLUDED.cached_at
            """)
            
            await db.execute(
                query,
                {
                    "id": exercise.id,
                    "name": exercise.name,
                    "description": exercise.description,
                    "category_id": exercise.category_id,
                    "category_name": exercise.category_name,
                    "muscles": muscles_json,
                    "muscles_secondary": muscles_secondary_json,
                    "equipment": equipment_json,
                    "image_url": exercise.image_url,
                    "cached_at": datetime.now(timezone.utc),
                },
            )
        
        await db.commit()
        logger.info(f"Successfully saved {len(exercises)} exercises to cache")

    async def _save_ingredients_to_cache(
        self, ingredients: list[WgerIngredientData], db: AsyncSession
    ) -> None:
        """
        Upsert ingredients vào wger_ingredients cache table.
        
        Requirements: 1.4
        """
        if not ingredients:
            return
        
        logger.info(f"Saving {len(ingredients)} ingredients to cache")
        
        for ingredient in ingredients:
            # Use raw SQL for upsert with ON CONFLICT
            query = text("""
                INSERT INTO wger_ingredients 
                    (id, name, energy, protein, carbohydrates, fat, fiber, sugar, cached_at)
                VALUES 
                    (:id, :name, :energy, :protein, :carbohydrates, :fat, :fiber, :sugar, :cached_at)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    energy = EXCLUDED.energy,
                    protein = EXCLUDED.protein,
                    carbohydrates = EXCLUDED.carbohydrates,
                    fat = EXCLUDED.fat,
                    fiber = EXCLUDED.fiber,
                    sugar = EXCLUDED.sugar,
                    cached_at = EXCLUDED.cached_at
            """)
            
            await db.execute(
                query,
                {
                    "id": ingredient.id,
                    "name": ingredient.name,
                    "energy": ingredient.energy,
                    "protein": ingredient.protein,
                    "carbohydrates": ingredient.carbohydrates,
                    "fat": ingredient.fat,
                    "fiber": ingredient.fiber,
                    "sugar": ingredient.sugar,
                    "cached_at": datetime.now(timezone.utc),
                },
            )
        
        await db.commit()
        logger.info(f"Successfully saved {len(ingredients)} ingredients to cache")

    async def _get_exercises_from_cache(self, db: AsyncSession) -> list[WgerExerciseData]:
        """Lấy exercises từ cache DB"""
        query = text("SELECT * FROM wger_exercises")
        result = await db.execute(query)
        rows = result.fetchall()
        
        exercises = []
        for row in rows:
            # Parse muscles
            muscles = [WgerMuscle(**m) for m in (row.muscles or [])]
            muscles_secondary = [WgerMuscle(**m) for m in (row.muscles_secondary or [])]
            equipment = [WgerEquipmentItem(**e) for e in (row.equipment or [])]
            
            exercises.append(
                WgerExerciseData(
                    id=row.id,
                    name=row.name,
                    description=row.description or "",
                    category_id=row.category_id,
                    category_name=row.category_name or "",
                    muscles=muscles,
                    muscles_secondary=muscles_secondary,
                    equipment=equipment,
                    image_url=row.image_url,
                )
            )
        
        return exercises

    async def _get_ingredients_from_cache(self, db: AsyncSession) -> list[WgerIngredientData]:
        """Lấy ingredients từ cache DB"""
        query = text("SELECT * FROM wger_ingredients")
        result = await db.execute(query)
        rows = result.fetchall()
        
        ingredients = []
        for row in rows:
            ingredients.append(
                WgerIngredientData(
                    id=row.id,
                    name=row.name,
                    energy=float(row.energy) if row.energy else None,
                    protein=float(row.protein) if row.protein else None,
                    carbohydrates=float(row.carbohydrates) if row.carbohydrates else None,
                    fat=float(row.fat) if row.fat else None,
                    fiber=float(row.fiber) if row.fiber else None,
                    sugar=float(row.sugar) if row.sugar else None,
                )
            )
        
        return ingredients

    def _parse_exercises(self, raw_data: list[dict]) -> list[WgerExerciseData]:
        """Parse raw API data thành WgerExerciseData objects"""
        exercises = []
        
        for item in raw_data:
            try:
                # Parse muscles
                muscles = []
                for m in item.get("muscles", []):
                    muscles.append(
                        WgerMuscle(
                            id=m.get("id", 0),
                            name_en=m.get("name_en", m.get("name", "")),
                            is_front=m.get("is_front", True),
                        )
                    )
                
                muscles_secondary = []
                for m in item.get("muscles_secondary", []):
                    muscles_secondary.append(
                        WgerMuscle(
                            id=m.get("id", 0),
                            name_en=m.get("name_en", m.get("name", "")),
                            is_front=m.get("is_front", True),
                        )
                    )
                
                # Parse equipment
                equipment = []
                for e in item.get("equipment", []):
                    equipment.append(
                        WgerEquipmentItem(
                            id=e.get("id", 0),
                            name=e.get("name", ""),
                        )
                    )
                
                # Get category info
                category = item.get("category", {})
                category_id = category.get("id") if isinstance(category, dict) else category
                category_name = category.get("name", "") if isinstance(category, dict) else ""
                
                # Get image URL (first image if available)
                images = item.get("images", [])
                image_url = images[0].get("image") if images else None
                
                exercises.append(
                    WgerExerciseData(
                        id=item["id"],
                        name=item.get("name", ""),
                        description=item.get("description", ""),
                        category_id=category_id,
                        category_name=category_name,
                        muscles=muscles,
                        muscles_secondary=muscles_secondary,
                        equipment=equipment,
                        image_url=image_url,
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing exercise {item.get('id')}: {e}")
                continue
        
        return exercises

    def _parse_ingredients(self, raw_data: list[dict]) -> list[WgerIngredientData]:
        """Parse raw API data thành WgerIngredientData objects"""
        ingredients = []
        
        for item in raw_data:
            try:
                ingredients.append(
                    WgerIngredientData(
                        id=item["id"],
                        name=item.get("name", ""),
                        energy=item.get("energy"),
                        protein=item.get("protein"),
                        carbohydrates=item.get("carbohydrates"),
                        fat=item.get("fat"),
                        fiber=item.get("fiber"),
                        sugar=item.get("sugar"),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing ingredient {item.get('id')}: {e}")
                continue
        
        return ingredients


# Singleton instance
wger_service = WgerService()
