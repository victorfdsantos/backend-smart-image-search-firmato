import reflex as rx
from pydantic import BaseModel
from app.api_client import get_products, image_url


class ProductSummary(BaseModel):
    id_produto: int = 0
    imagem_url: str = ""


class State(rx.State):
    search_text: str = ""        # ← var declarada
    selected_image: str = "" 
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 1
    is_loading: bool = False
    products: list[ProductSummary] = []

    def select_image(self, url: str): 
        self.selected_image = url    

    def set_search_text(self, text: str):
        self.search_text = text
        self.page = 1

    def on_load(self):
        self.load_products()

    def load_products(self):
        self.is_loading = True
        data = get_products(page=self.page, page_size=self.page_size)
        self.total = data.get("total", 0)
        self.total_pages = data.get("total_pages", 1)
        self.products = [
            ProductSummary(
                id_produto=item["id_produto"],
                imagem_url=image_url(item["id_produto"]),
            )
            for item in data.get("items", [])
        ]
        self.is_loading = False

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            self.load_products()

    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            self.load_products()