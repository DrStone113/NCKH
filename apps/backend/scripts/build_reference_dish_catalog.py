"""Build a reproducible Vietnamese reference-recipe catalog.

The source snapshot is ViFoodRec (PACLIC 2024), pinned to a Git commit and
restricted to recipes originating from Ajinomoto Vietnam's ``Món Ngon Mỗi
Ngày``.  Nutrition is recalculated from the bundled Vietnam Food Composition
Table; website calorie fields are never copied.

Run from ``apps/backend``::

    python scripts/build_reference_dish_catalog.py --source path/to/foods.csv

Without ``--source`` the script downloads the pinned public research snapshot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
FOODS_FILE = BACKEND_DIR / "data" / "vietnamese_foods.json"
BASE_DISHES_FILE = BACKEND_DIR / "data" / "vietnamese_dishes.json"
CURATED_DISHES_FILE = BACKEND_DIR / "data" / "vietnamese_dishes_curated_v1.json"
OUTPUT_FILE = BACKEND_DIR / "data" / "vietnamese_dishes_reference_v1.json"

SOURCE_COMMIT = "126caa3a8b58708a09b2b2e119ff4923b6f06d82"
SOURCE_SHA256 = "79a8135e108a6ff1b66338737b816aa1021522b44ae902c98b439398194fcadb"
SOURCE_URL = (
    "https://raw.githubusercontent.com/QuocAn55/"
    "A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-"
    f"Recommendation-System/{SOURCE_COMMIT}/Data/Clean%20Dataset/foods.csv"
)
SOURCE_REPOSITORY_URL = (
    "https://github.com/QuocAn55/"
    "A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-"
    f"Recommendation-System/tree/{SOURCE_COMMIT}/Data/Clean%20Dataset"
)
ACADEMIC_REFERENCE_URL = "https://aclanthology.org/2024.paclic-1.4/"
TARGET_LIVE_COUNT = 300
REFERENCE_START_ID = 98
MIN_INGREDIENTS = 2
MIN_WEIGHT_COVERAGE = 0.60

GRAM_PATTERN = re.compile(
    r"(?:^|,\s*)([^,;:]+?)(?:\s*:\s*|\s+)(\d+(?:[.,]\d+)?)\s*(kg|g)\b",
    re.IGNORECASE,
)
SERVINGS_PATTERN = re.compile(r"(\d+)\s*người", re.IGNORECASE)

# These are synonym/description normalizations, never cross-species
# substitutions. Rules are ordered from specific to general.
FOOD_ALIASES: tuple[tuple[str, str], ...] = (
    ("bánh phở", "Bánh phở"),
    ("bún gạo", "Bún"),
    ("bún tươi", "Bún"),
    ("bún", "Bún"),
    ("miến dong", "Miến dong"),
    ("miến", "Miến dong"),
    ("bún tàu", "Miến dong"),
    ("bột nếp", "Bột gạo nếp"),
    ("bột gạo nếp", "Bột gạo nếp"),
    ("bột gạo", "Bột gạo tẻ"),
    ("bột mì", "Bột mì"),
    ("gạo nếp", "Gạo nếp cái"),
    ("gạo tẻ", "Gạo tẻ máy"),
    ("gạo thơm", "Gạo tẻ máy"),
    ("gạo", "Gạo tẻ máy"),
    ("nếp", "Gạo nếp cái"),
    ("khoai lang", "Khoai lang"),
    ("khoai môn", "Khoai môn"),
    ("khoai sọ", "Khoai sọ"),
    ("khoai tây", "Khoai tây"),
    ("khoai mì", "Củ sắn"),
    ("bột năng", "Bột sắn"),
    ("củ sắn", "Củ đậu"),
    ("củ đậu", "Củ đậu"),
    ("đậu xanh", "Đậu xanh (đậu tắt)"),
    ("đậu hà lan", "Đậu Hà Lan"),
    ("đậu cô ve", "Đậu cô ve"),
    ("đậu cove", "Đậu cô ve"),
    ("đậu que", "Đậu cô ve"),
    ("đậu đũa", "Đậu đũa"),
    ("đậu hũ", "Đậu phụ"),
    ("đậu phụ", "Đậu phụ"),
    ("tàu hũ ky", "Đậu phụ chúc"),
    ("tàu hũ ki", "Đậu phụ chúc"),
    ("đậu phộng", "Lạc hạt"),
    ("lạc", "Lạc hạt"),
    ("hạt điều", "Hạt điều"),
    ("hạt sen tươi", "Hạt sen tươi"),
    ("hạt sen", "Hạt sen khô"),
    ("mè", "Vừng (đen, trắng)"),
    ("vừng", "Vừng (đen, trắng)"),
    ("bí đỏ", "Bí ngô"),
    ("bí ngô", "Bí ngô"),
    ("bí đao", "Bí đao (bí xanh)"),
    ("cà chua bi", "Cà chua"),
    ("cà chua", "Cà chua"),
    ("cà rốt", "Cà rốt (củ đỏ, vàng)"),
    ("cà tím", "Cà tím"),
    ("cải bắp tím", "Cải bắp đỏ"),
    ("bắp cải tím", "Cải bắp đỏ"),
    ("bắp cải", "Cải bắp"),
    ("cải thìa", "Cải thìa (cải trắng)"),
    ("cải bẹ xanh", "Cải xanh"),
    ("cải xanh", "Cải xanh"),
    ("cải xoong", "Cải soong"),
    ("xà lách xoong", "Cải soong"),
    ("bông cải xanh", "Súp lơ xanh"),
    ("bông cải trắng", "Súp lơ trắng"),
    ("súp lơ xanh", "Súp lơ xanh"),
    ("súp lơ trắng", "Súp lơ trắng"),
    ("bắp non", "Ngô bao tử"),
    ("bắp mỹ", "Ngô bắp tươi"),
    ("bắp hạt", "Ngô bắp tươi"),
    ("ngô", "Ngô bắp tươi"),
    ("bột bắp", "Bột ngô vàng"),
    ("bột báng", "Trân châu sắn"),
    ("củ cải trắng", "Củ cải trắng"),
    ("ngó sen", "Ngó sen"),
    ("dưa leo", "Dưa chuột"),
    ("dưa chuột", "Dưa chuột"),
    ("dưa cải chua", "Dưa cải bẹ"),
    ("cải chua", "Dưa cải bẹ"),
    ("măng chua", "Măng chua"),
    ("măng tây", "Măng tây"),
    ("măng luộc", "Măng tre"),
    ("măng tre", "Măng tre"),
    ("giá đậu xanh", "Giá đậu xanh"),
    ("giá sống", "Giá đậu xanh"),
    ("giá", "Giá đậu xanh"),
    ("hành lá", "Hành lá (hành hoa)"),
    ("hành tây", "Hành tây"),
    ("hành tím", "Hành củ tươi"),
    ("hành củ", "Hành củ tươi"),
    ("cần tây", "Cần tây"),
    ("hành boaro", "Tỏi tây (cả lá)"),
    ("hành poaro", "Tỏi tây (cả lá)"),
    ("hẹ lá", "Hẹ lá"),
    ("bông hẹ", "Hẹ lá"),
    ("hẹ", "Hẹ lá"),
    ("hoa chuối", "Hoa chuối"),
    ("bắp chuối", "Hoa chuối"),
    ("bông thiên lý", "Hoa lý"),
    ("rau mồng tơi", "Rau mồng tơi"),
    ("mồng tơi", "Rau mồng tơi"),
    ("đọt mồng tơi", "Rau mồng tơi"),
    ("rau muống", "Rau muống"),
    ("rau răm", "Rau răm"),
    ("rau ngót", "Rau ngót"),
    ("rau mùi tàu", "Rau mùi tàu"),
    ("ngò gai", "Rau mùi tàu"),
    ("ngò rí", "Rau mùi"),
    ("rau mùi", "Rau mùi"),
    ("rau thơm", "Rau thơm"),
    ("húng lủi", "Rau húng"),
    ("húng quế", "Rau húng"),
    ("rau quế", "Rau húng"),
    ("lá quế", "Rau húng"),
    ("lá lốt", "Lá lốt"),
    ("tía tô", "Tía tô"),
    ("lá tía tô", "Tía tô"),
    ("thì là", "Thìa là"),
    ("xà lách", "Rau sà lách"),
    ("rau má", "Rau má, má mơ"),
    ("su hào", "Su hào"),
    ("su su", "Su su, quả"),
    ("nấm đông cô khô", "Nấm hương khô"),
    ("nấm hương khô", "Nấm hương khô"),
    ("nấm đông cô tươi", "Nấm hương tươi"),
    ("nấm hương tươi", "Nấm hương tươi"),
    ("nấm hương", "Nấm hương khô"),
    ("nấm mỡ", "Nấm mỡ (Nấm tây)"),
    ("nấm rơm", "Nấm rơm"),
    ("mộc nhĩ", "Mộc nhĩ"),
    ("nấm mèo", "Mộc nhĩ"),
    ("dứa", "Dứa ta"),
    ("thơm", "Dứa ta"),
    ("dừa nạo", "Cùi dừa già"),
    ("dừa bào", "Cùi dừa già"),
    ("đu đủ xanh", "Đu đủ xanh"),
    ("đu đủ", "Đu đủ chín"),
    ("táo tây", "Táo tây"),
    ("táo", "Táo tây"),
    ("dâu tây", "Dâu tây"),
    ("kiwi", "Quả kiwi"),
    ("bơ trái", "Quả bơ vỏ xanh"),
    ("quả bơ", "Quả bơ vỏ xanh"),
    ("bơ lạt", "Bơ"),
    ("dầu mè", "Dầu mè"),
    ("dầu ô liu", "Dầu oliu"),
    ("dầu oliu", "Dầu oliu"),
    ("dầu ăn", "Dầu thảo mộc (Lạc, vừng, cám...)"),
    ("mỡ heo", "Mỡ lợn nước"),
    ("mỡ lợn", "Mỡ lợn nước"),
    ("mỡ phần", "Thịt lợn mỡ"),
    ("mỡ gáy", "Thịt lợn mỡ"),
    ("thịt ba chỉ", "Thịt lợn nửa nạc, nửa mỡ"),
    ("thịt ba rọi", "Thịt lợn nửa nạc, nửa mỡ"),
    ("ba rọi", "Thịt lợn nửa nạc, nửa mỡ"),
    ("thit ba roi", "Thịt lợn nửa nạc, nửa mỡ"),
    ("thịt heo nạc", "Thịt lợn nạc"),
    ("thịt heo xay", "Thịt lợn nạc"),
    ("thịt lợn nạc", "Thịt lợn nạc"),
    ("thịt nạc dăm", "Thịt lợn nạc"),
    ("thịt nạc vai", "Thịt lợn nạc"),
    ("thịt nạc lưng", "Thịt lợn nạc"),
    ("nạc dăm", "Thịt lợn nạc"),
    ("sườn heo", "Sườn lợn"),
    ("sườn lợn", "Sườn lợn"),
    ("sườn non", "Sườn lợn"),
    ("chân giò", "Chân giò lợn"),
    ("giò lụa", "Giò lụa"),
    ("chả lụa", "Giò lụa"),
    ("dăm bông", "Dăm bông lợn"),
    ("thịt bò phi lê", "Thịt bò, lưng, nạc"),
    ("bò phi lê", "Thịt bò, lưng, nạc"),
    ("thịt bò thăn", "Thịt bò, lưng, nạc"),
    ("thịt bò", "Thịt bò loại I"),
    ("bắp bò", "Thịt bò loại I"),
    ("gan heo", "Gan lợn"),
    ("tim heo", "Tim lợn"),
    ("dồi trường", "Lòng lợn (ruột non)"),
    ("mề gà", "Mề gà"),
    ("tai heo", "Tai lợn"),
    ("lưỡi heo", "Lưỡi lợn"),
    ("huyết heo", "Tiết lợn sống"),
    ("bì", "Bì lợn"),
    ("thịt dê", "Thịt dê, nạc"),
    ("thịt gân bò", "Gân chân bò"),
    ("thịt vịt", "Thịt vịt"),
    ("cá hồi", "Cá hồi"),
    ("cá chép", "Cá chép"),
    ("cá lóc", "Cá quả"),
    ("cá quả", "Cá quả"),
    ("cá thu", "Cá thu"),
    ("cá ngừ", "Cá ngừ"),
    ("cá nục", "Cá nục"),
    ("cá trê", "Cá trê"),
    ("cá trắm", "Cá trắm cỏ"),
    ("cá rô phi", "Cá rô phi"),
    ("cá rô", "Cá rô đồng"),
    ("cá thác lác", "Cá lác"),
    ("cua đồng", "Cua đồng"),
    ("cua biển", "Cua bể"),
    ("thịt cua", "Cua bể"),
    ("cua xay", "Cua đồng"),
    ("ghẹ", "ghẹ"),
    ("hải sâm", "Hải sâm"),
    ("hến", "Hến"),
    ("thịt hến", "Hến"),
    ("lươn", "Lươn"),
    ("mực khô", "Mực khô"),
    ("mực", "Mực tươi"),
    ("ốc bươu", "ốc bươu"),
    ("sò", "Sò"),
    ("tôm khô", "Tôm khô"),
    ("tôm sú", "Tôm biển"),
    ("tôm biển", "Tôm biển"),
    ("tôm đồng", "Tôm đồng"),
    ("trứng cút", "Trứng chim cút"),
    ("trứng vịt", "Trứng vịt"),
    ("trứng gà", "Trứng gà"),
    ("đùi ếch", "ếch (thịt đùi)"),
    ("thịt ếch", "ếch (thịt đùi)"),
    ("sữa tươi", "Sữa bò tươi"),
    ("sữa đặc", "Sữa đặc có đường Việt Nam"),
    ("phô mai", "Pho mát"),
    ("ớt chuông đỏ", "ớt đỏ to"),
    ("ớt đà lạt đỏ", "ớt đỏ to"),
    ("ớt chuông vàng", "ớt vàng to"),
    ("ớt đà lạt vàng", "ớt vàng to"),
    ("ớt chuông xanh", "ớt xanh to"),
    ("đường", "Đường kính"),
    ("mật ong", "Mật ong"),
    ("gừng", "Gừng tươi"),
    ("nghệ tươi", "Nghệ tươi"),
    ("riềng", "Riềng"),
    ("tỏi", "Tỏi ta"),
    ("me", "Quả me chua"),
    ("khế", "Khế"),
    ("kiệu chua", "Kiệu muối"),
    ("cốm", "Cốm"),
    ("mắm tép chua", "Mắm tép chua"),
)

EXCLUDED_RAW_TERMS = (
    " chay",
    "chay ",
    "giả",
    "topping",
    "thanh cua",
    "xông khói",
)
EXCLUDED_DISH_TERMS = (
    "pancake",
    "pizza",
    "spaghetti",
    "sushi",
    "hamburger",
    "sandwich",
    "taco",
    "latte",
    "cocktail",
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold().strip(" .:-")
    return re.sub(r"\s+", " ", value)


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _source_path(source: Path | None) -> tuple[Path, bool]:
    if source is not None:
        return source, False
    temporary = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    temporary.close()
    target = Path(temporary.name)
    urllib.request.urlretrieve(SOURCE_URL, target)
    return target, True


def _verify_source(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"unexpected ViFoodRec SHA-256: {digest}")


def _match_food(raw_name: str, valid_names: set[str]) -> str | None:
    normalized = _normalize(raw_name)
    if any(term in normalized for term in EXCLUDED_RAW_TERMS):
        return None
    for alias, food_name in FOOD_ALIASES:
        if normalized == alias or normalized.startswith(f"{alias} "):
            if food_name not in valid_names:
                raise ValueError(f"alias target missing from food table: {food_name}")
            return food_name
    return None


def _parse_ingredients(
    text: str,
    servings: int,
    foods_by_name: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], float, int]:
    quantified_weight = 0.0
    matched_weight = 0.0
    matched: defaultdict[str, float] = defaultdict(float)
    source_names: defaultdict[str, set[str]] = defaultdict(set)
    for raw_name, raw_amount, unit in GRAM_PATTERN.findall(text):
        amount = float(raw_amount.replace(",", "."))
        grams = amount * (1000.0 if unit.casefold() == "kg" else 1.0)
        if not 0 < grams <= 5000:
            continue
        quantified_weight += grams
        food_name = _match_food(raw_name, set(foods_by_name))
        if food_name is None:
            continue
        matched[food_name] += grams / servings
        source_names[food_name].add(_normalize(raw_name))
        matched_weight += grams

    coverage = matched_weight / quantified_weight if quantified_weight else 0.0
    ingredients = [
        {
            "name": name,
            "grams": round(grams, 1),
            "category": _food_group(int(foods_by_name[name]["ma_so"])),
            "source_names": sorted(source_names[name]),
        }
        for name, grams in sorted(matched.items())
        if grams >= 0.5
    ]
    return ingredients, coverage, len(GRAM_PATTERN.findall(text))


def _food_group(code: int) -> str:
    if 1000 <= code < 3000 or 12000 <= code < 13000:
        return "carb"
    if 3000 <= code < 4000:
        return "protein"
    if 4000 <= code < 5000:
        return "veggie"
    if 5000 <= code < 6000:
        return "fruit"
    if 6000 <= code < 7000:
        return "fat"
    if 7000 <= code < 10000:
        return "protein"
    if 10000 <= code < 11000:
        return "dairy"
    return "seasoning"


def _meal_types(name: str) -> list[str]:
    normalized = _normalize(name)
    breakfast_terms = ("phở", "bún", "mì", "miến", "cháo", "xôi", "bánh")
    snack_terms = ("bánh", "chè", "sinh tố", "nước", "trái cây")
    result = ["lunch", "dinner"]
    if any(term in normalized for term in breakfast_terms):
        result.insert(0, "breakfast")
    if any(term in normalized for term in snack_terms):
        result.append("snack")
    return result


def _family(name: str) -> str:
    normalized = _normalize(name)
    groups = (
        ("soup", ("canh", "súp", "lẩu", "cháo")),
        ("noodle", ("phở", "bún", "mì", "miến", "hủ tiếu")),
        ("seafood", ("cá", "tôm", "mực", "cua", "ghẹ", "ốc", "hến")),
        ("poultry", ("gà", "vịt", "chim")),
        ("meat", ("bò", "heo", "lợn", "sườn", "thịt")),
        ("vegetable", ("rau", "nấm", "đậu", "chay")),
        ("snack", ("bánh", "xôi", "chè")),
    )
    for family, terms in groups:
        if any(term in normalized for term in terms):
            return family
    return "other"


def _calories(
    ingredients: list[dict[str, Any]],
    foods_by_name: dict[str, dict[str, Any]],
) -> float:
    return sum(
        float(foods_by_name[item["name"]]["energy_kcal"])
        * float(item["grams"])
        / 100.0
        for item in ingredients
    )


def principal_ingredients_present(
    dish_name: str,
    ingredients: list[dict[str, Any]],
    foods_by_name: dict[str, dict[str, Any]],
) -> bool:
    """Reject recipes whose named main ingredient was lost in normalization."""

    normalized = _normalize(dish_name)
    if "chay" in normalized:
        return True
    codes = {int(foods_by_name[item["name"]]["ma_so"]) for item in ingredients}

    if "chim cút" in normalized:
        if "trứng" not in normalized or 9007 not in codes:
            return False
    if "bò" in normalized and "bò bía" not in normalized:
        beef_codes = {
            *range(7001, 7007),
            7029,
            7033,
            7035,
            7037,
            7039,
            7043,
            7044,
            7049,
            7051,
            7055,
            7058,
            7061,
            7068,
            7075,
            11017,
        }
        if not codes & beef_codes:
            return False

    pork_codes = {
        *range(7016, 7019),
        7030,
        7031,
        7032,
        7034,
        7036,
        7038,
        7041,
        *range(7045, 7048),
        7050,
        7052,
        7053,
        7054,
        7057,
        7059,
        7060,
        *range(7062, 7068),
        *range(7069, 7075),
        11019,
        11020,
    }

    rules = (
        ("gà", lambda code: code in {7013, 7040, 7048, 7056, 7082, 9001}),
        ("vịt", lambda code: code in {7028, 7042, 9004, 9010, 11021}),
        ("heo", lambda code: code in pork_codes),
        ("lợn", lambda code: code in pork_codes),
        ("ếch", lambda code: code == 7080),
        ("cá", lambda code: 8001 <= code <= 8032 or code in {8057, 8058}),
        ("tôm", lambda code: code in {8051, 8052, 8053, 8059}),
        ("mực", lambda code: code in {8039, 8040}),
        ("cua", lambda code: code in {8033, 8034}),
        ("ghẹ", lambda code: code == 8035),
        ("hến", lambda code: code == 8037),
        ("nghêu", lambda code: code == 8054),
        ("lươn", lambda code: code == 8038),
        ("ốc", lambda code: 8041 <= code <= 8044),
        ("hàu", lambda code: False),
        ("bạch tuộc", lambda code: False),
        ("sò", lambda code: code == 8048),
        ("bún", lambda code: code == 1020),
        ("phở", lambda code: code == 1013),
        ("miến", lambda code: code == 2015),
        ("cháo", lambda code: 1001 <= code <= 1005),
        ("cơm", lambda code: 1001 <= code <= 1005),
        ("xôi", lambda code: code in {1001, 1002}),
        ("nấm", lambda code: 4121 <= code <= 4126),
        ("đậu hũ", lambda code: 3025 <= code <= 3027),
        ("đậu phụ", lambda code: 3025 <= code <= 3027),
    )
    return all(
        term not in normalized or any(predicate(code) for code in codes)
        for term, predicate in rules
    )


def _candidates(source: Path) -> list[dict[str, Any]]:
    foods = _read_json(FOODS_FILE)
    foods_by_name = {food["name"]: food for food in foods}
    base = _read_json(BASE_DISHES_FILE)
    curated = _read_json(CURATED_DISHES_FILE)
    used_names = {
        _normalize(dish["name"])
        for dish in [*base, *curated.get("overrides", []), *curated.get("additions", [])]
    }
    results: list[dict[str, Any]] = []
    with source.open(encoding="utf-8-sig", newline="") as file_handle:
        for row in csv.DictReader(file_handle):
            if "monngonmoingay.com" not in row.get("image_link", ""):
                continue
            name = str(row.get("dish_name", "")).strip()
            normalized_name = _normalize(name)
            if (
                not name
                or normalized_name in used_names
                or any(term in normalized_name for term in EXCLUDED_DISH_TERMS)
            ):
                continue
            servings_match = SERVINGS_PATTERN.search(row.get("serving_size", ""))
            if not servings_match:
                continue
            servings = int(servings_match.group(1))
            if not 1 <= servings <= 12:
                continue
            ingredients, coverage, quantified_count = _parse_ingredients(
                row.get("ingredients", ""), servings, foods_by_name
            )
            if len(ingredients) < MIN_INGREDIENTS or coverage < MIN_WEIGHT_COVERAGE:
                continue
            calories = _calories(ingredients, foods_by_name)
            if not 60 <= calories <= 1200:
                continue
            groups = {item["category"] for item in ingredients}
            if "protein" not in groups and "carb" not in groups:
                continue
            if not principal_ingredients_present(
                name, ingredients, foods_by_name
            ):
                continue
            results.append(
                {
                    "source_food_id": int(row["food_id"]),
                    "name": name,
                    "meal_types": _meal_types(name),
                    "ingredients": ingredients,
                    "estimated_calories": round(calories),
                    "catalog_status": "normalized_reference_recipe",
                    "normalization": {
                        "source_servings": servings,
                        "matched_ingredient_count": len(ingredients),
                        "quantified_ingredient_count": quantified_count,
                        "quantified_weight_coverage": round(coverage, 4),
                        "nutrition_basis": (
                            "Matched quantified ingredients per serving; "
                            "unquantified water and seasonings are omitted"
                        ),
                    },
                    "provenance": {
                        "publisher": "Món Ngon Mỗi Ngày - Công ty Ajinomoto Việt Nam",
                        "source_title": name,
                        "source_url": SOURCE_REPOSITORY_URL,
                        "source_record_id": int(row["food_id"]),
                        "source_image_url": row.get("image_link", ""),
                        "dataset": "ViFoodRec",
                        "academic_reference_url": ACADEMIC_REFERENCE_URL,
                        "retrieved_at": "2026-08-26",
                        "calculation_method": (
                            "FAO/INFOODS ingredient-sum calculation using the "
                            "Vietnam Food Composition Table"
                        ),
                    },
                    "_family": _family(name),
                    "_quality": (
                        len(groups),
                        len(ingredients),
                        coverage,
                        -int(row["food_id"]),
                    ),
                }
            )
            used_names.add(normalized_name)
    return results


def _select(candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    by_family: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_family[candidate["_family"]].append(candidate)
    for items in by_family.values():
        items.sort(key=lambda item: item["_quality"], reverse=True)

    selected: list[dict[str, Any]] = []
    family_order = sorted(by_family)
    while len(selected) < count:
        progressed = False
        for family in family_order:
            if by_family[family] and len(selected) < count:
                selected.append(by_family[family].pop(0))
                progressed = True
        if not progressed:
            break
    if len(selected) < count:
        raise ValueError(f"only {len(selected)} reference recipes passed validation")

    selected.sort(key=lambda item: item["source_food_id"])
    for dish_id, item in enumerate(selected, start=REFERENCE_START_ID):
        item["id"] = dish_id
        item.pop("_family", None)
        item.pop("_quality", None)
    return selected


def build(source: Path | None = None) -> dict[str, Any]:
    source_path, remove_after = _source_path(source)
    try:
        _verify_source(source_path)
        current_live_count = len(_read_json(BASE_DISHES_FILE)) + len(
            _read_json(CURATED_DISHES_FILE).get("additions", [])
        )
        additions_needed = TARGET_LIVE_COUNT - current_live_count
        selected = _select(_candidates(source_path), additions_needed)
        return {
            "schema_version": 1,
            "catalog_version": "vifoodrec-normalized-v1-2026-08-26",
            "source": {
                "dataset": "ViFoodRec",
                "source_commit": SOURCE_COMMIT,
                "source_sha256": SOURCE_SHA256,
                "source_url": SOURCE_REPOSITORY_URL,
                "academic_reference_url": ACADEMIC_REFERENCE_URL,
                "source_snapshot_rows": 4000,
                "eligible_recipe_origin_rows": 1146,
                "recipe_origin": "Món Ngon Mỗi Ngày - Công ty Ajinomoto Việt Nam",
                "usage_note": (
                    "The paper states free research access; confirm the upstream "
                    "dataset and recipe-site terms before commercial redistribution"
                ),
            },
            "quality_policy": {
                "minimum_matched_ingredients": MIN_INGREDIENTS,
                "minimum_quantified_weight_coverage": MIN_WEIGHT_COVERAGE,
                "calorie_source": "Vietnam Food Composition Table 2007",
                "food_matching": (
                    "Auditable Vietnamese synonyms and the closest applicable "
                    "food-table group; normalized records are not promoted to "
                    "verified_recipe"
                ),
                "website_nutrition_fields_used": False,
            },
            "additions": selected,
        }
    finally:
        if remove_after:
            source_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    payload = build(args.source)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(payload['additions'])} reference recipes to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
