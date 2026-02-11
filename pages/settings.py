from nicegui import ui
from layout.main_area import PageContext
from services.i18n import t


def render(container: ui.element, ctx: PageContext) -> None:
    with container:
        ui.label(t("settings.title", "Settings")).classes("text-2xl font-bold")
        with ui.card().classes("mt-4 w-full"):
            ui.switch(t("settings.enable_feature_x", "Enable feature X"), value=True)
            ui.input(t("settings.display_name", "Display name")).classes("w-full")
