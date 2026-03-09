import requests

API_BASE = "http://localhost:8000"

def get_products(page: int = 1, page_size: int = 20) -> dict:
    try:
        resp = requests.get(
            f"{API_BASE}/products",
            params={"page": page, "page_size": page_size},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"page": page, "page_size": page_size, "total": 0, "total_pages": 1, "items": []}

def image_url(product_id: int) -> str:
    return f"{API_BASE}/products/images/{product_id}.jpg"