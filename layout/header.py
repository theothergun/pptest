from datetime import datetime

from nicegui import ui

from layout.main_area import PageContext
from auth.session import get_user, logout


def build_header(ctx: PageContext) -> ui.header:
    header = ui.header().classes("h-16 w-full")

    with header:
        with ui.row().classes("h-full items-center w-full px-4"):
            ui.label("SOME CUSTOM LABEL").classes("text-lg font-semibold")
            ui.space()

            # Toggle Nav
            ui.button(
                "Toggle Nav",
                icon="menu",
                on_click=lambda: ctx.drawer.toggle() if ctx.drawer else None,
            ).props("flat color=white no-caps")

            # Live date/time (right next to Toggle Nav)
            dt_label = ui.label("").classes("ml-3 text-sm text-white/90")

            def update_time() -> None:
                # You can change the format as you like
                dt_label.set_text(datetime.now().strftime("%d-%m-%Y %H:%M"))

            update_time()
            ui.timer(60.0, update_time)

            # User info (icon + username)
            user = get_user()
            username = user.username if user else "unknown"

            with ui.row().classes("ml-4 items-center gap-2"):
                ui.icon("account_circle").classes("text-white/90")
                ui.label(username).classes("text-sm text-white/90")

            # Logout
            def do_logout() -> None:
                logout()
                ui.run_javascript("window.location.href = '/login'")

            ui.button("Logout", icon="logout", on_click=do_logout).props("flat color=white no-caps") \
                .classes("ml-2")

    return header
