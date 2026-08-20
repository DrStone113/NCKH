from modules.wger.router import (
    _cache_get,
    _cache_put,
    _main_image_url,
    _strip_html,
)
from collections import OrderedDict


def test_strip_html_decodes_entities_and_preserves_list_lines() -> None:
    source = "<p>Push &amp; pull</p><ul><li>Keep&nbsp;control</li></ul>"
    cleaned = _strip_html(source)

    assert "Push & pull" in cleaned
    assert "• Keep control" in cleaned
    assert "<p>" not in cleaned


def test_main_image_url_prefers_wger_main_image() -> None:
    assert _main_image_url(
        [
            {"image": "fallback.jpg", "is_main": False},
            {"image": "main.jpg", "is_main": True},
        ]
    ) == "main.jpg"
    assert _main_image_url(None) is None


def test_proxy_cache_is_bounded_lru() -> None:
    cache: OrderedDict[str, bytes] = OrderedDict()
    _cache_put(cache, "first", b"1", 2)
    _cache_put(cache, "second", b"2", 2)
    assert _cache_get(cache, "first") == b"1"

    _cache_put(cache, "third", b"3", 2)

    assert list(cache) == ["first", "third"]
    assert _cache_get(cache, "second") is None
