"""
WgerSearchService — tìm bài tập thực từ wger API trực tiếp.

Gọi /api/v2/exerciseinfo/ với params category/muscles/equipment,
không dùng cache DB để tránh delay sync.
"""

import logging
import re
from dataclasses import dataclass, field

import httpx

from config import settings

logger = logging.getLogger(__name__)

# ─── Mapping keyword → wger category_id ────────────────────────────────────
# wger: 10=Abs, 8=Arms, 12=Back, 14=Calves, 11=Chest, 9=Legs, 13=Shoulders
CATEGORY_MAP: dict[str, int] = {
    "bụng": 10, "core": 10, "ab": 10, "abs": 10,
    "tay": 8, "arm": 8, "bicep": 8, "tricep": 8, "cánh tay": 8,
    "lưng": 12, "back": 12,
    "bắp chân": 14, "calf": 14, "calves": 14,
    "ngực": 11, "chest": 11,
    "chân": 9, "leg": 9, "squat": 9, "lunge": 9, "đùi": 9,
    "vai": 13, "shoulder": 13,
}

# Mapping keyword → wger muscle_id
# wger muscles: 1=Biceps, 2=Anterior deltoid, 3=Serratus anterior,
#   4=Pectoralis major, 5=Triceps, 6=Rectus abdominis, 7=Gastrocnemius,
#   8=Gluteus maximus, 9=Quadriceps, 10=Hamstrings, 11=Calves,
#   12=Latissimus dorsi, 13=Trapezius, 14=Obliques
MUSCLE_ID_MAP: dict[str, list[int]] = {
    "ngực": [4], "chest": [4],
    "lưng": [12, 13], "back": [12, 13],
    "chân": [9, 10, 8], "leg": [9, 10],
    "vai": [2], "shoulder": [2],
    "tay": [1, 5], "arm": [1, 5],
    "bicep": [1], "biceps": [1],
    "tricep": [5], "triceps": [5],
    "bụng": [6, 14], "core": [6, 14], "abs": [6],
    "mông": [8], "glute": [8],
    "bắp chân": [7, 11], "calf": [7],
}

# Mapping keyword → wger equipment_id
# wger: 1=Barbell, 3=Dumbbell, 6=Pull-up bar, 7=None/Bodyweight,
#       10=Kettlebell, 11=Cable, 12=Machine, 14=Resistance band
EQUIPMENT_ID_MAP: dict[str, list[int]] = {
    "không có dụng cụ": [7], "bodyweight": [7], "không": [7],
    "tạ tay": [3], "dumbbell": [3], "tạ đơn": [3],
    "tạ đòn": [1], "barbell": [1],
    "dây kháng lực": [14], "resistance band": [14], "dây": [14],
    "xà": [6], "pull-up bar": [6], "xà đơn": [6],
    "kettlebell": [10],
    "cable": [11], "cáp": [11],
    "máy": [12], "machine": [12],
    "gym": [1, 3, 11, 12],
    "đầy đủ dụng cụ gym": [1, 3, 11, 12],
}

TIMEOUT = httpx.Timeout(connect=8.0, read=15.0, write=5.0, pool=5.0)


@dataclass
class ExerciseSearchParams:
    category_ids: list[int] = field(default_factory=list)
    muscle_ids: list[int] = field(default_factory=list)
    equipment_ids: list[int] = field(default_factory=list)
    limit: int = 8


@dataclass
class WgerExercise:
    id: int
    name: str
    description: str
    category_name: str
    muscles: list[str]          # muscle name_en
    equipment: list[str]        # equipment name


class WgerSearchService:
    """Tìm bài tập thực từ wger API, inject vào prompt để LLM không tự bịa."""

    def parse_search_params(self, message: str, enriched_message: str = "") -> ExerciseSearchParams:
        """Parse message → ExerciseSearchParams."""
        text = (enriched_message or message).lower()
        params = ExerciseSearchParams()

        # Toàn thân → lấy nhiều category
        if re.search(r"toàn thân|full body|tất cả nhóm cơ", text):
            params.category_ids = [10, 8, 12, 11, 9, 13]
            return params

        # Category
        for kw, cat_id in CATEGORY_MAP.items():
            if kw in text and cat_id not in params.category_ids:
                params.category_ids.append(cat_id)

        # Muscle ids
        for kw, m_ids in MUSCLE_ID_MAP.items():
            if kw in text:
                for m in m_ids:
                    if m not in params.muscle_ids:
                        params.muscle_ids.append(m)

        # Equipment ids
        for kw, eq_ids in EQUIPMENT_ID_MAP.items():
            if kw in text:
                for eq in eq_ids:
                    if eq not in params.equipment_ids:
                        params.equipment_ids.append(eq)

        # "tại nhà" → bodyweight
        if not params.equipment_ids and re.search(r"tại nhà|ở nhà|home", text):
            params.equipment_ids = [7]

        logger.debug(
            "SearchParams: cat=%s muscles=%s equip=%s",
            params.category_ids, params.muscle_ids, params.equipment_ids,
        )
        return params

    async def search_exercises(self, params: ExerciseSearchParams) -> list[WgerExercise]:
        """
        Gọi wger /api/v2/exerciseinfo/ với params.
        Thử theo thứ tự ưu tiên:
        1. category + equipment (nếu có cả hai)
        2. category only
        3. muscles only
        4. fallback: lấy page đầu không filter
        """
        exercises: list[WgerExercise] = []

        async with httpx.AsyncClient(
            base_url=settings.wger_base_url,
            timeout=TIMEOUT,
        ) as client:
            # Thử 1: category + equipment
            if params.category_ids and params.equipment_ids:
                exercises = await self._fetch(
                    client,
                    category=params.category_ids[0],
                    equipment=params.equipment_ids[0],
                    limit=params.limit,
                )

            # Thử 2: category only
            if len(exercises) < 3 and params.category_ids:
                exercises = await self._fetch(
                    client,
                    category=params.category_ids[0],
                    limit=params.limit,
                )

            # Thử 3: muscles only
            if len(exercises) < 3 and params.muscle_ids:
                exercises = await self._fetch(
                    client,
                    muscles=params.muscle_ids[0],
                    limit=params.limit,
                )

            # Fallback: không filter, lấy page đầu
            if len(exercises) < 3:
                exercises = await self._fetch(client, limit=params.limit)

        return exercises[:params.limit]

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        category: int | None = None,
        muscles: int | None = None,
        equipment: int | None = None,
        limit: int = 8,
    ) -> list[WgerExercise]:
        """Gọi /exerciseinfo/ với params, parse kết quả."""
        query: dict = {
            "format": "json",
            "language": 2,       # English
            "limit": limit * 2,  # lấy nhiều hơn để lọc bỏ không có tên
            "offset": 0,
        }
        if category is not None:
            query["category"] = category
        if muscles is not None:
            query["muscles"] = muscles
        if equipment is not None:
            query["equipment"] = equipment

        try:
            resp = await client.get("/exerciseinfo/", params=query)
            if resp.status_code != 200:
                logger.warning("wger API %s → %d", resp.url, resp.status_code)
                return []
            data = resp.json()
        except httpx.TimeoutException:
            logger.warning("wger API timeout (category=%s muscles=%s equip=%s)", category, muscles, equipment)
            return []
        except Exception as e:
            logger.warning("wger API error: %s", e)
            return []

        exercises = []
        for item in data.get("results", []):
            ex = self._parse_item(item)
            if ex:
                exercises.append(ex)

        logger.info(
            "wger fetch: cat=%s muscles=%s equip=%s → %d exercises",
            category, muscles, equipment, len(exercises),
        )
        return exercises

    def _parse_item(self, item: dict) -> WgerExercise | None:
        """Parse một exerciseinfo item thành WgerExercise."""
        try:
            # Lấy translation tiếng Anh (language=2), fallback sang đầu tiên
            translations = item.get("translations", [])
            en = next((t for t in translations if t.get("language") == 2), None)
            trans = en or (translations[0] if translations else {})

            name = trans.get("name", "").strip()
            if not name:
                return None  # bỏ qua bài tập không có tên

            # Strip HTML từ description
            raw_desc = trans.get("description", "")
            description = re.sub(r"<[^>]+>", " ", raw_desc).strip()
            description = re.sub(r"\s+", " ", description)[:120]

            # Category
            cat = item.get("category", {})
            category_name = cat.get("name", "") if isinstance(cat, dict) else ""

            # Muscles (primary)
            muscles = [
                m.get("name_en") or m.get("name", "")
                for m in item.get("muscles", [])
                if m.get("name_en") or m.get("name")
            ]

            # Equipment
            equipment = [
                e.get("name", "")
                for e in item.get("equipment", [])
                if e.get("name")
            ]

            return WgerExercise(
                id=item["id"],
                name=name,
                description=description,
                category_name=category_name,
                muscles=muscles,
                equipment=equipment,
            )
        except Exception as e:
            logger.debug("Parse error for item id=%s: %s", item.get("id"), e)
            return None

    def format_for_prompt(self, exercises: list[WgerExercise]) -> str:
        """
        Format danh sách bài tập thực để inject vào system prompt.
        LLM PHẢI dùng các bài tập này, KHÔNG tự bịa tên khác.
        """
        if not exercises:
            return ""

        lines = [
            "Bài tập thực từ wger (PHẢI dùng các bài tập này, KHÔNG tự bịa tên khác):"
        ]
        for ex in exercises:
            muscles_str = ", ".join(ex.muscles) if ex.muscles else ""
            equip_str = ", ".join(ex.equipment) if ex.equipment else "Bodyweight"

            line = f"[WGER_EXERCISE id={ex.id}] {ex.name}"
            if ex.category_name:
                line += f" | {ex.category_name}"
            if muscles_str:
                line += f" | Cơ: {muscles_str}"
            if equip_str:
                line += f" | Dụng cụ: {equip_str}"
            if ex.description:
                line += f" | {ex.description}"
            lines.append(line)

        lines.append(
            "\nQUY TẮC BẮT BUỘC: Chỉ dùng tên và id từ danh sách trên. "
            "Điền wger_id = id tương ứng trong [ACTION_DATA]. "
            "KHÔNG thêm bài tập không có trong danh sách."
        )
        return "\n".join(lines)


# Singleton
wger_search_service = WgerSearchService()
