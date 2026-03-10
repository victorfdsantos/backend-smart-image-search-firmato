import asyncio
import base64
import reflex as rx
from pydantic import BaseModel
from app.api_client import get_products, search_products, image_url


class ProductSummary(BaseModel):
    id_produto: str = ""
    imagem_url: str = ""


class State(rx.State):
    search_text: str = ""
    selected_image: str = ""
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 1
    is_loading: bool = False
    is_searching: bool = False
    products: list[ProductSummary] = []
    uploaded_image: str = ""   # base64 para preview
    _image_bytes: bytes = b""  # bytes para enviar ao backend (privado de instância, não var de estado)

    async def on_load(self):
        await self.load_products()

    # ------------------------------------------------------------------
    # Upload de imagem
    # ------------------------------------------------------------------

    async def handle_upload(self, files: list[rx.UploadFile]):
        if not files:
            return
        file = files[0]
        self._image_bytes = await file.read()
        b64 = base64.b64encode(self._image_bytes).decode()
        self.uploaded_image = f"data:image/jpeg;base64,{b64}"
        # Dispara busca imediatamente com a imagem
        yield State.run_search(self.search_text)

    async def clear_image(self):
        self._image_bytes = b""
        self.uploaded_image = ""

        # Se tem texto, busca só por texto
        if self.search_text.strip():
            yield State.run_search(self.search_text)
        else:
            # Sem texto e sem imagem → volta galeria normal
            await self.load_products()

    # ------------------------------------------------------------------
    # Busca com debounce (texto)
    # ------------------------------------------------------------------

    @rx.event(background=True)
    async def set_search_text(self, text: str):
        async with self:
            self.search_text = text
            self.page = 1

        # Se limpou tudo e não tem imagem, volta para galeria normal
        if not text.strip() and not self._image_bytes:
            async with self:
                await self.load_products()
            return

        # Debounce de 500ms
        await asyncio.sleep(0.5)

        # Cancela se usuário continuou digitando
        async with self:
            current_text = self.search_text
        if current_text != text:
            return

        yield State.run_search(text)

    @rx.event(background=True)
    async def run_search(self, text: str):
        async with self:
            self.is_searching = True
            image_bytes = self._image_bytes
            query = text.strip() or None

        data = await search_products(
            query=query,
            image_bytes=image_bytes if image_bytes else None,
        )

        async with self:
            self.total = data.get("total", 0)
            self.total_pages = 1
            self.products = [
                ProductSummary(
                    id_produto=str(item["id_produto"]),
                    imagem_url=f"http://localhost:8000{item['imagem_url']}",
                )
                for item in data.get("items", [])
            ]
            self.is_searching = False

    # ------------------------------------------------------------------
    # Galeria paginada normal
    # ------------------------------------------------------------------

    async def load_products(self):
        self.is_loading = True
        data = await get_products(page=self.page, page_size=self.page_size)
        self.total = data.get("total", 0)
        self.total_pages = data.get("total_pages", 1)
        self.products = [
            ProductSummary(
                id_produto=str(item["id_produto"]),
                imagem_url=image_url(item["id_produto"]),
            )
            for item in data.get("items", [])
        ]
        self.is_loading = False

    async def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            await self.load_products()

    async def prev_page(self):
        if self.page > 1:
            self.page -= 1
            await self.load_products()

    def select_image(self, url: str):
        self.selected_image = url