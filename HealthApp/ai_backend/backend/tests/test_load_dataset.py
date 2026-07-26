"""Tests for the knowledge-base loader (``scripts/load_dataset.py``).

The loader is the only thing standing between the RAG corpus and an empty
table, so its correctness is worth pinning down. The most important assertion
here is the last one: no misaligned mineral column may leak into user-facing
text.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_LOADER = Path(__file__).resolve().parents[1] / "scripts" / "load_dataset.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("load_dataset_under_test", _LOADER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def loader():
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("asyncpg")
    return _load_module()


# --------------------------------------------------------------------------- #
# Identity / idempotency
# --------------------------------------------------------------------------- #

def test_chunk_ids_are_deterministic(loader):
    """Re-running the loader must not duplicate the corpus."""
    first = loader._chunk_id("food", "Gạo nếp cái")
    second = loader._chunk_id("food", "Gạo nếp cái")
    assert first == second


def test_chunk_ids_differ_across_categories(loader):
    assert loader._chunk_id("food", "Plank") != loader._chunk_id("exercise", "Plank")


def test_collected_chunks_have_unique_ids(loader):
    chunks = loader.collect_chunks()
    assert len({c["id"] for c in chunks}) == len(chunks)


# --------------------------------------------------------------------------- #
# Corpus size
# --------------------------------------------------------------------------- #

def test_corpus_covers_all_four_sources(loader):
    """Guards the original bug: only 21 of ~637 records were being loaded."""
    chunks = loader.collect_chunks()
    assert len(chunks) > 600, f"expected the full corpus, got {len(chunks)}"

    categories = {c["category"] for c in chunks}
    assert categories == {"food", "exercise"}


def test_no_chunk_is_too_short_to_embed(loader):
    for chunk in loader.collect_chunks():
        assert len(chunk["content"]) >= 60, chunk["title"]


# --------------------------------------------------------------------------- #
# Data quality — the misaligned mineral columns
# --------------------------------------------------------------------------- #

def test_unreliable_columns_never_reach_the_text(loader):
    """``vietnamese_foods.json`` has a column shift from ``magnesium`` on.

    Its ``zinc`` field actually holds sodium, ``sodium`` holds potassium, and
    so on. Emitting those as labelled nutrients would hand users confidently
    wrong numbers.

    The match is on "<nutrient> <number><unit>" rather than the bare word:
    several foods are legitimately named after one of these words ("cua đồng",
    "cá rô đồng"), and a substring check flags those as violations.
    """
    import re

    forbidden = ("kẽm", "kali", "magie", "natri", "phospho", "mangan", "đồng")
    pattern = re.compile(
        r"\b(" + "|".join(forbidden) + r")\s+[\d.,]+\s*(mg|g|µg|μg)\b",
        re.IGNORECASE,
    )
    blob = " ".join(c["content"] for c in loader.collect_chunks())
    leaked = pattern.findall(blob)
    assert not leaked, f"misaligned nutrient columns leaked into text: {leaked[:5]}"


def test_guard_would_catch_a_real_leak(loader):
    """The guard above is only useful if it can actually fail."""
    import re

    forbidden = ("kẽm", "kali", "magie", "natri", "phospho", "mangan", "đồng")
    pattern = re.compile(
        r"\b(" + "|".join(forbidden) + r")\s+[\d.,]+\s*(mg|g|µg|μg)\b",
        re.IGNORECASE,
    )
    assert pattern.search("Vi chất: canxi 55mg, kẽm 158mg.")   # a real leak
    assert not pattern.search("Cua đồng (Crab, fresh water).")  # a food name


def test_no_label_rule_uses_an_unreliable_field(loader):
    used = {rule[0] for rule in loader._LABEL_RULES}
    assert not (used & loader.UNRELIABLE_FIELDS)


def test_metadata_excludes_unreliable_fields(loader):
    keys: set[str] = set()
    for chunk in loader.collect_chunks():
        keys |= set(chunk["metadata"])
    assert not (keys & loader.UNRELIABLE_FIELDS)


# --------------------------------------------------------------------------- #
# Labelling
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "food,expected",
    [
        ("Thịt bò loại I", "giàu đạm"),
        ("Cam", "giàu vitamin C"),
        ("Cùi dừa già", "nhiều béo"),
        ("Trứng gà", "nhiều cholesterol"),
    ],
)
def test_nutrition_labels_match_reality(loader, food, expected):
    """Labels are what make "món nào giàu đạm" retrievable at all.

    A raw figure like "21g" carries no "giàu" semantics for the embedding
    model; the label supplies it.
    """
    import json

    data_dir = Path(loader.DATA_DIR)
    foods = json.loads((data_dir / "vietnamese_foods.json").read_text(encoding="utf-8"))
    item = next(f for f in foods if f["name"] == food)
    assert expected in loader.nutrition_labels(item)


def test_missing_values_do_not_produce_labels(loader):
    assert loader.nutrition_labels({}) == []
    assert loader.nutrition_labels({"protein": None, "fat": "-"}) == []


def test_num_coerces_table_placeholders(loader):
    assert loader._num("-") is None
    assert loader._num("") is None
    assert loader._num(None) is None
    assert loader._num("12.5") == 12.5
    assert loader._num(7) == 7.0


# --------------------------------------------------------------------------- #
# Food grouping
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "ma_so,expected",
    [
        (1001, "Ngũ cốc và sản phẩm chế biến"),
        (4103, "Rau, củ, quả dùng làm rau"),
        (7001, "Thịt và sản phẩm chế biến"),
        (9001, "Trứng và sản phẩm chế biến"),
        (0, "Thực phẩm khác"),
    ],
)
def test_food_group_from_ma_so(loader, ma_so, expected):
    assert loader.food_group({"ma_so": ma_so}) == expected


def test_food_text_cites_its_source(loader):
    text = loader.make_food_text({
        "name": "Gạo tẻ máy", "ma_so": 1001,
        "energy_kcal": 344, "protein": 7.9,
    })
    assert "Viện Dinh dưỡng" in text
    assert "344" in text
