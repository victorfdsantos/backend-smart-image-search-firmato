import httpx

API_BASE = "http://localhost:8000"

async def get_products(page: int = 1, page_size: int = 20) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{API_BASE}/products",
                params={"page": page, "page_size": page_size},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"page": page, "page_size": page_size, "total": 0, "total_pages": 1, "items": []}

def image_url(product_id: int) -> str:
    return f"{API_BASE}/static/images/{product_id}.jpg"