from collections import OrderedDict

import pytest

from modules.wger.router import (
    _cache_get,
    _cache_put,
    _main_image_url,
    search_ingredients,
    _strip_html,
)


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


@pytest.mark.asyncio
async def test_ingredient_search_route_proxies_the_collection_endpoint(monkeypatch) -> None:
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "count": 1,
                "next": None,
                "results": [
                    {
                        "id": 42,
                        "name": "Rice",
                        "energy": 130,
                        "protein": 2.7,
                        "carbohydrates": 28,
                        "fat": 0.3,
                    }
                ],
            }

    class Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, params):
            captured["url"] = url
            captured["params"] = params
            return Response()

    monkeypatch.setattr("modules.wger.router.httpx.AsyncClient", Client)

    result = await search_ingredients(name="rice", page=2, language=2)

    assert captured["url"].endswith("/ingredient/")
    assert captured["params"] == {
        "format": "json",
        "page": 2,
        "language": 2,
        "name": "rice",
    }
    assert result["results"][0]["id"] == 42
