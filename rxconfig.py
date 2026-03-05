import reflex as rx


config = rx.Config(
    app_name="app",
    frontend_port=3000,
    backend_port=8000,
    # Desabilitar plugins não utilizados
    disable_plugins=[
        'reflex.plugins.sitemap.SitemapPlugin',
    ],
    # Configurações adicionais
    telemetry_enabled=False,
)