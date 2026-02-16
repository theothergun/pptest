from nicegui import ui
from layout.context import PageContext


def build_main_area(ctx: PageContext) -> None:
    ctx.breadcrumb = None
    # full width + full height so pages can use h-full and push actions down
    ctx.main_area = ui.column().classes("w-full h-full min-h-0 gap-4 overflow-hidden")
