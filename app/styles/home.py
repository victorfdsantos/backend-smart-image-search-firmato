import reflex as rx

# Paleta de cores inspirada no site Firmato
COLORS = {
    "background": "#f8f8f8",
    "surface": "#ffffff",
    "text_primary": "#2c2c2c",
    "text_secondary": "#6b6b6b",
    "accent": "#a67c52",
    "accent_light": "#d4b08c",
    "border": "#eaeaea",
    "border_dark": "#dddddd",
}

# Estilos base reutilizáveis com Lato
def get_base_text_style(size="16px", weight="400", color=None):
    return {
        "font_family": "Lato, sans-serif",  # Mudado para Lato
        "font_size": size,
        "font_weight": weight,
        "color": color if color else COLORS["text_primary"],
        "line_height": "1.5",
    }

def get_base_heading_style(size="24px", weight="400"):
    return {
        "font_family": "Lato, sans-serif", 
        "font_size": size,
        "font_weight": weight,
        "color": COLORS["text_primary"],
        "letter_spacing": "-0.02em",
    }

# Topbar styles
topbar_style = {
    "width": "100%",
    "padding": "20px 40px",
    "background_color": COLORS["surface"],
    "border_bottom": f"1px solid {COLORS['border']}",
    "position": "sticky",
    "top": "0",
    "z_index": "100",
}

topbar_title_style = {
    "font_family": "Lato, sans-serif",  # Mudado para Lato (ou mantenha DM Serif se preferir)
    "font_size": "24px",
    "font_weight": "900",  # Peso mais bold para o logo
    "color": COLORS["text_primary"],
    "letter_spacing": "0.02em",
    "text_transform": "uppercase",
}

# Button styles
base_button_style = {
    "border_radius": "2px",
    "padding": "10px 24px",
    "font_family": "Lato, sans-serif",  # Mudado para Lato
    "font_size": "14px",
    "font_weight": "400",
    "cursor": "pointer",
    "transition": "all 0.2s ease",
    "letter_spacing": "0.02em",
    "text_transform": "uppercase",
}

outline_button_style = {
    **base_button_style,
    "background_color": "transparent",
    "border": f"1px solid {COLORS['border_dark']}",
    "color": COLORS["text_primary"],
    "_hover": {
        "background_color": COLORS["background"],
        "border_color": COLORS["accent"],
        "color": COLORS["accent"],
    }
}

solid_button_style = {
    **base_button_style,
    "background_color": COLORS["accent"],
    "border": f"1px solid {COLORS['accent']}",
    "color": "#ffffff",
    "_hover": {
        "background_color": COLORS["accent_light"],
        "border_color": COLORS["accent_light"],
    }
}

# Panel styles
panel_style = {
    "background_color": COLORS["surface"],
    "border": f"1px solid {COLORS['border']}",
    "padding": "28px",
    "width": "100%",
}

# Image card styles
image_card_style = {
    "border_radius": "2px",
    "overflow": "hidden",
    "border": f"1px solid {COLORS['border']}",
    "transition": "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    "background_color": COLORS["surface"],
    "cursor": "pointer",
    "_hover": {
        "border_color": COLORS["accent"],
        "transform": "translateY(-4px)",
        "box_shadow": "0 12px 24px -8px rgba(0,0,0,0.1)",
    }
}

# Pagination button style
pagination_button_style = {
    **base_button_style,
    "background_color": "transparent",
    "border": f"1px solid {COLORS['border']}",
    "color": COLORS["text_primary"],
    "min_width": "44px",
    "padding": "8px 20px",
    "_hover": {
        "background_color": COLORS["background"],
        "border_color": COLORS["accent"],
        "color": COLORS["accent"],
    },
    "_disabled": {
        "opacity": "0.5",
        "cursor": "not-allowed",
        "_hover": {
            "background_color": "transparent",
            "border_color": COLORS["border"],
            "color": COLORS["text_primary"],
        }
    }
}

# Upload area styles
upload_area_style = {
    "border": f"1px dashed {COLORS['border_dark']}",
    "border_radius": "2px",
    "background_color": COLORS["background"],
    "padding": "0",
    "width": "100%",
    "transition": "all 0.2s ease",
    "_hover": {
        "border_color": COLORS["accent"],
        "background_color": f"{COLORS['accent_light']}10",
    }
}

# Logo styles
logo_style = {
    "height": "40px",
    "width": "auto",
    "object_fit": "contain",
    "cursor": "pointer",
    "transition": "opacity 0.2s ease",
    "_hover": {
        "opacity": "0.8",
    }
}