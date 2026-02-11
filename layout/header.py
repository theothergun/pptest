from datetime import datetime

from nicegui import ui

from layout.main_area import PageContext
from auth.session import get_user, logout
from services.i18n import SUPPORTED_LANGUAGES, get_language, set_language, t


def build_header(ctx: PageContext) -> ui.header:
    header = ui.header().classes("h-16 w-full")

    with header:
        with ui.row().classes("h-full items-center w-full px-4"):
            ui.label(t("app.title", "Shopfloor application")).classes("text-lg font-semibold")
            ui.space()

            language_options = {entry["code"]: entry["label"] for entry in SUPPORTED_LANGUAGES}

            def on_language_change(e) -> None:
                lang = set_language(e.value)
                ui.notify(f"Language switched to: {language_options[lang]}", type="positive")
                ui.run_javascript("location.reload()")

            ui.select(
                options=language_options,
                value=get_language(),
                on_change=on_language_change,
                label="Language",
            ).props("dense outlined bg-color=white").classes("min-w-[180px] text-black")

            # Toggle Nav
            ui.button(
                t("header.toggle_nav", "Toggle Nav"),
                icon="menu",
                on_click=lambda: ctx.drawer.toggle() if ctx.drawer else None,
            ).props("flat color=white no-caps")

            # Live date/time (right next to Toggle Nav)
            dt_label = ui.label("").classes("ml-3 text-sm text-white/90")

            def update_time() -> None:
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

            ui.button(t("header.logout", "Logout"), icon="logout", on_click=do_logout).props("flat color=white no-caps") \
                .classes("ml-2")

    return header