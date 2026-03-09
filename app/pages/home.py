import reflex as rx
from app.state import State, ProductSummary
from app.styles import home as styles


def topbar():
    return rx.hstack(
        rx.image(
            src="/logo_cinza.png",
            height="40px",
            width="auto",
            alt="Firmato",
        ),
        rx.spacer(),
        rx.hstack(
            rx.button(
                "Importar Dados",
                style=styles.outline_button_style,
            ),
            rx.button(
                "Sobre",
                style=styles.outline_button_style,
            ),
            spacing="3",
        ),
        style=styles.topbar_style,
    )


def search_panel():
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="search", size=20, color=styles.COLORS["accent"]),
            rx.heading(
                "Buscar Imagens",
                style=styles.get_base_heading_style("20px"),
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.text(
            "Faça upload de uma imagem ou busque por texto",
            style=styles.get_base_text_style("14px", color=styles.COLORS["text_secondary"]),
        ),
        rx.upload(
            rx.vstack(
                rx.button(
                    rx.hstack(
                        rx.icon(tag="upload", size=16),
                        rx.text("Escolher imagem"),
                        spacing="2",
                    ),
                    style=styles.solid_button_style,
                    width="100%",
                ),
                rx.text(
                    "ou arraste e solte",
                    style=styles.get_base_text_style("12px", color=styles.COLORS["text_secondary"]),
                ),
                spacing="2",
                width="100%",
                padding="12px",
                align="center",
            ),
            border=f"1px dashed {styles.COLORS['border_dark']}",
            border_radius="2px",
            background_color=styles.COLORS["background"],
            padding="0",
            width="100%",
            max_width="100%",
            height="auto",
            _hover={
                "border_color": styles.COLORS["accent"],
                "background_color": f"{styles.COLORS['accent_light']}10",
            },
        ),
        rx.input(
            placeholder="Digite sua busca...",
            value=State.search_text,
            on_change=State.set_search_text,
            border=f"1px solid {styles.COLORS['border_dark']}",
            border_radius="2px",
            background_color=styles.COLORS["surface"],
            color=styles.COLORS["text_primary"],
            placeholder_color=styles.COLORS["text_primary"],
            padding="6px 16px",
            font_family="Inter, sans-serif",
            font_size="14px",
            _focus={
                "border_color": styles.COLORS["accent"],
                "border_width": "1px",
                "box_shadow": f"0 0 0 2px {styles.COLORS['accent_light']}20",
                "outline": "none",
            },
            _hover={
                "border_color": styles.COLORS["accent"],
            },
            width="100%",
        ),
        rx.button(
            rx.hstack(
                rx.icon(tag="filter", size=16),
                rx.text("Filtros avançados"),
                spacing="2",
            ),
            style=styles.outline_button_style,
            width="100%",
        ),
        spacing="4",
        width="100%",
    )

def image_card(product: ProductSummary):
    return rx.box(
        rx.image(
            src=product.imagem_url,
            width="100%",
            height="240px",
            object_fit="cover",
        ),
        style=styles.image_card_style,
        on_click=State.select_image(product.imagem_url),
    )

def image_grid():
    return rx.cond(
        State.products.length() > 0,
        rx.grid(
            rx.foreach(State.products, image_card),
            columns="3",
            spacing="4",
            width="100%",
        ),
        rx.center(
            rx.vstack(
                rx.icon(tag="image", size=48, color=styles.COLORS["border_dark"]),
                rx.text(
                    "Nenhum produto encontrado",
                    style=styles.get_base_text_style("16px", color=styles.COLORS["text_secondary"]),
                ),
                spacing="4",
            ),
            padding="48px",
            width="100%",
        ),
    )



def pagination_controls():
    return rx.hstack(
        rx.button(
            rx.hstack(
                rx.icon(tag="chevron-left", size=16),
                rx.text("Anterior"),
                spacing="1",
            ),
            on_click=State.prev_page,
            style=styles.pagination_button_style,
            is_disabled=State.page <= 1,
        ),
        rx.text(
            f"{State.page} / {State.total_pages}",
            style=styles.get_base_text_style("14px", color=styles.COLORS["text_secondary"]),
            min_width="60px",
            text_align="center",
        ),
        rx.button(
            rx.hstack(
                rx.text("Próxima"),
                rx.icon(tag="chevron-right", size=16),
                spacing="1",
            ),
            on_click=State.next_page,
            style=styles.pagination_button_style,
            is_disabled=State.page >= State.total_pages,
        ),
        spacing="4",
        justify="center",
        width="100%",
    )


def preview_panel():
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="eye", size=20, color=styles.COLORS["accent"]),
            rx.heading(
                "Pré-visualização",
                style=styles.get_base_heading_style("20px"),
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.divider(border_color=styles.COLORS["border"], width="100%"),
        rx.cond(
            State.selected_image != "",
            rx.vstack(
                rx.box(
                    rx.image(
                        src=State.selected_image,
                        width="100%",
                        max_height="1000px",
                        object_fit="contain",
                        border_radius="2px",
                    ),
                    border=f"1px solid {styles.COLORS['border']}",
                    padding="4px",
                    width="100%",
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon(tag="copy", size=16),
                            rx.text("Copiar imagem"),
                            spacing="2",
                        ),
                        style=styles.outline_button_style,
                        flex="1",
                    ),
                    rx.button(
                        rx.hstack(
                            rx.icon(tag="download", size=16),
                            rx.text("Download"),
                            spacing="2",
                        ),
                        style=styles.solid_button_style,
                        flex="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            rx.center(
                rx.vstack(
                    rx.icon(tag="image", size=64, color=styles.COLORS["border"]),
                    rx.text(
                        "Selecione uma imagem",
                        style=styles.get_base_text_style("16px", color=styles.COLORS["text_secondary"]),
                    ),
                    rx.text(
                        "Clique em qualquer imagem para visualizar",
                        style=styles.get_base_text_style("14px", color=styles.COLORS["text_secondary"]),
                    ),
                    spacing="3",
                ),
                height="600px",
                width="100%",
                border=f"2px dashed {styles.COLORS['border']}",
                background_color=styles.COLORS["background"],
                padding="48px",
            ),
        ),
        style=styles.panel_style,
        width="100%",
        spacing="4",
    )

def left_panel():
    return rx.vstack(
        search_panel(),
        rx.divider(border_color=styles.COLORS["border"], width="100%"),
        rx.hstack(
            rx.text(
                "Resultados",
                style=styles.get_base_text_style("16px", weight="500"),
            ),
            rx.spacer(),
            rx.text(
                State.total.to_string() + " produtos",
                style=styles.get_base_text_style("14px", color=styles.COLORS["text_secondary"]),
            ),
            width="100%",
        ),
        image_grid(),
        pagination_controls(),
        style=styles.panel_style,
        width="100%",
        spacing="5",
    )


def home():
    return rx.vstack(
        topbar(),
        rx.hstack(
            rx.box(
                left_panel(),
                flex="0 0 38%",
                padding="32px 16px 32px 32px",
            ),
            rx.box(
                preview_panel(),
                flex="1",
                padding="32px 32px 32px 16px",
            ),
            width="100%",
            align_items="stretch",
            spacing="0",
        ),
        width="100%",
        background_color=styles.COLORS["background"],
        min_height="100vh",
        spacing="0",
        on_mount=State.on_load,
    )