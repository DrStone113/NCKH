"""
Open Food Facts proxy endpoints — tránh CORS khi chạy Flutter Web.
Dùng API v2 (search) thay vì CGI để tránh rate limit.
Docs: https://openfoodfacts.github.io/openfoodfacts-server/api/
"""
import asyncio
import logging
import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/off", tags=["open-food-facts"])

OFF_BASE = "https://world.openfoodfacts.org"

TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=5.0, pool=5.0)

HEADERS = {
    "User-Agent": "HealthApp/1.0 (healthapp@example.com)",
    "Accept": "application/json",
}

_PRODUCT_FIELDS = (
    "code,product_name,product_name_vi,brands,quantity,"
    "image_front_url,image_front_small_url,nutriscore_grade,"
    "nutriments,serving_size,serving_quantity"
)


@router.get("/search")
async def search_products(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=20),
):
    """Tìm kiếm sản phẩm qua OFF API v2 — ít bị rate limit hơn CGI."""
    # Dùng API v2 search endpoint
    url = f"{OFF_BASE}/api/v2/search"
    params = {
        "search_terms": q.strip(),
        "fields": _PRODUCT_FIELDS,
        "page": str(page),
        "page_size": str(min(page_size, 10)),
        "sort_by": "unique_scans_n",  # Sắp xếp theo phổ biến
    }

    logger.info("🌍 [OFF] Search v2: q=%s page=%d", q, page)

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params)
            logger.info("📡 [OFF] v2 response: %d (%.2f KB)", resp.status_code, len(resp.content) / 1024)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 503:
                raise HTTPException(
                    status_code=503,
                    detail="Open Food Facts tạm thời không khả dụng. Thử lại sau.",
                )

            logger.error("❌ [OFF] Search failed: %d — %s", resp.status_code, resp.text[:100])
            raise HTTPException(status_code=502, detail=f"Open Food Facts lỗi {resp.status_code}")

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Open Food Facts timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Không kết nối được Open Food Facts")
    except Exception as e:
        logger.error("💥 [OFF] Search error: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/product/{barcode}")
async def get_product(barcode: str):
    """Lấy sản phẩm theo barcode."""
    url = f"{OFF_BASE}/api/v2/product/{barcode.strip()}.json"
    params = {"fields": _PRODUCT_FIELDS}

    logger.info("🌍 [OFF] Barcode: %s", barcode)

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params)
            logger.info("📡 [OFF] Barcode response: %d", resp.status_code)

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return {"status": 0, "status_verbose": "product not found"}

            raise HTTPException(status_code=502, detail=f"Open Food Facts lỗi {resp.status_code}")

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Open Food Facts timeout")
    except Exception as e:
        logger.error("💥 [OFF] Barcode error: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/health")
async def off_health():
    """Kiểm tra kết nối đến Open Food Facts."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0), headers=HEADERS) as client:
            resp = await client.get(
                f"{OFF_BASE}/api/v2/product/3017620422003.json",
                params={"fields": "code,product_name"},
            )
            return {
                "status": "ok" if resp.status_code == 200 else "error",
                "off_status_code": resp.status_code,
            }
    except Exception as e:
        return {"status": "error", "detail": str(e)}
