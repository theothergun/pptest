from nicegui import ui
from layout.main_area import PageContext


def render(container: ui.element, ctx:PageContext) -> None:
    with container:
        ui.label("Reports").classes("text-2xl font-bold")
        with ui.card().classes("mt-4 w-full"):
            ui.label("Example report card")
            ui.linear_progress(value=0.6)
