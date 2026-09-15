"""Pre-serialized HTTP cache for immutable public nutrition catalogs."""

from __future__ import annotations

import hashlib
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CatalogHttpCacheMiddleware(BaseHTTPMiddleware):
    """Add ETag/304 and reuse serialized bytes for full public catalogs."""

    _FULL_REQUESTS = frozenset(
        {
            ("/api/nutrition/vietnamese-dishes", ""),
            ("/api/nutrition/vietnamese-dishes", "limit=500"),
            ("/api/nutrition/vietnamese-foods", ""),
            ("/api/nutrition/vietnamese-foods", "limit=1000"),
        }
    )

    def __init__(self, app, *, max_entries: int = 4) -> None:
        super().__init__(app)
        self._entries: OrderedDict[tuple[str, str], tuple[bytes, str, str]] = OrderedDict()
        self._max_entries = max_entries

    async def dispatch(self, request: Request, call_next):
        key = (request.url.path, request.url.query)
        if request.method != "GET" or key not in self._FULL_REQUESTS:
            return await call_next(request)

        cached = self._entries.get(key)
        if cached is not None:
            body, etag, content_type = cached
            self._entries.move_to_end(key)
            if request.headers.get("if-none-match") == etag:
                return Response(
                    status_code=304,
                    headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
                )
            return Response(
                body,
                media_type=content_type,
                headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
            )

        response = await call_next(request)
        if response.status_code != 200:
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        content_type = response.headers.get("content-type", "application/json").split(";", 1)[0]
        self._entries[key] = (body, etag, content_type)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        if request.headers.get("if-none-match") == etag:
            return Response(
                status_code=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
            )
        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers.update({"ETag": etag, "Cache-Control": "public, max-age=86400"})
        return Response(
            body,
            status_code=response.status_code,
            media_type=content_type,
            headers=headers,
        )


__all__ = ["CatalogHttpCacheMiddleware"]
