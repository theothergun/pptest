from nicegui import ui
from layout.main_area import PageContext
from services.i18n import t


def render(container: ui.element, ctx:PageContext) -> None:
    with container:
        ui.label(t("reports.title", "Reports")).classes("text-2xl font-bold")
        with ui.card().classes("mt-4 w-full"):
            ui.label(t("reports.example_card", "Example report card"))
            ui.linear_progress(value=0.6)
