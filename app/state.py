import reflex as rx


class State(rx.State):
    """Estado principal da aplicação."""
    
    # Propriedades com valores padrão
    search_text: str = ""
    selected_image: str = ""

    page: int = 1
    page_size: int = 6

    images: list[str] = [
        f"https://placehold.co/600x600?text=Imagem+{i+1}"
        for i in range(60)
    ]

    @rx.var
    def total_pages(self) -> int:
        """Calcula o total de páginas."""
        return (len(self.images) + self.page_size - 1) // self.page_size

    @rx.var
    def paginated_images(self) -> list[str]:
        """Retorna as imagens da página atual."""
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.images[start:end]
    
    @rx.var
    def total_images(self) -> int:
        """Retorna o total de imagens (para uso no template)."""
        return len(self.images)

    def set_search_text(self, text: str):
        """Setter explícito para search_text."""
        self.search_text = text
        # Resetar para primeira página quando buscar
        self.page = 1

    def set_selected_image(self, image: str):
        """Setter explícito para selected_image."""
        self.selected_image = image

    def next_page(self):
        """Vai para a próxima página."""
        if self.page < self.total_pages:
            self.page += 1

    def prev_page(self):
        """Vai para a página anterior."""
        if self.page > 1:
            self.page -= 1

    def select_image(self, img: str):
        """Seleciona uma imagem para visualização."""
        self.selected_image = img