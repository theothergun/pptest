import os
from nicegui import ui, app

from layout.main_area import PageContext, build_main_area, navigate
from layout.header import build_header
from layout.footer import build_footer
from layout.drawer import build_drawer

HEADER_PX = 64 #h-16
FOOTER_PX = 48 #h-12

@ui.page("/")
def index():
    ui.colors(primary="#3b82f6")

    # per-user default state
    if "current_route" not in app.storage.user:
        app.storage.user["current_route"] = "home"

    # context object is created fresh per user/page load (SAFE)
    ctx = PageContext()

    # Top-level layout elements must be top-level:
    build_header(ctx)
    build_drawer(ctx)
    build_footer()

    # Main content area
    with ui.row().classes("w-full"):
        with ui.column().classes("w-full p-6 gap-4").style(
            f"height: calc(100vh - {HEADER_PX}px - {FOOTER_PX}px);"
        ):
            build_main_area(ctx)

    # initial page from user storage
    navigate(ctx, app.storage.user["current_route"])


ui.run(
    title="NiceGUI SPA",
    reload=False,
    storage_secret=os.environ["NICEGUI_STORAGE_SECRET"],
)
