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

async def search_products(query: str = None, image_bytes: bytes = None, top_k: int = 20) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            params = {"top_k": top_k}
            if query:
                params["q"] = query

            files = {"image": ("image.jpg", image_bytes, "image/jpeg")} if image_bytes else None

            resp = await client.post(
                f"{API_BASE}/search",
                params=params,
                files=files,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"total": 0, "items": []}