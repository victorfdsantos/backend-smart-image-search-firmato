import reflex as rx
from app.pages.home import home

app = rx.App(
    theme=rx.theme(
        appearance="light",
        has_background=True,
        radius="none",
        accent_color="gray"
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Lato:wght@300;400;700;900&display=swap"
    ],
)

app.add_page(
    home,
    route="/",
    title="Firmato - Buscador de Imagens",
    description="Buscador de imagens elegante inspirado no design Firmato",
)