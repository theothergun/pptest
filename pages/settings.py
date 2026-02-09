from nicegui import ui
from layout.main_area import PageContext


def render(container: ui.element, ctx: PageContext) -> None:
    with container:
        ui.label("Settings").classes("text-2xl font-bold")
        with ui.card().classes("mt-4 w-full"):
            ui.switch("Enable feature X", value=True)
            ui.input("Display name").classes("w-full")
