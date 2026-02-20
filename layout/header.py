from datetime import datetime

from nicegui import ui

from layout.main_area import PageContext
from auth.auth_service import unregister_itac_user
from auth.session import get_user, has_role, logout
from services.app_config import get_app_config, save_app_config
from services.i18n import SUPPORTED_LANGUAGES, get_language, set_language, t


def build_header(ctx: PageContext) -> ui.header:
    cfg = get_app_config()
    is_dark = bool(getattr(cfg.ui.navigation, "dark_mode", False))
    header = ui.header().classes("h-16 w-full app-header")

    with header:
        with ui.row().classes("h-full items-center w-full px-4"):
            # First icon on the left: drawer toggle (icon only)
            ui.button(
                icon="menu",
                on_click=lambda: ctx.drawer.toggle() if ctx.drawer else None,
            ).props("flat round dense").classes("mr-2")

            ui.label(t("app.title", "Shopfloor application")).classes("text-lg font-semibold")
            ui.space()

            ctx.device_panel_toggle_btn = ui.button(
                icon="monitor_heart",
                on_click=lambda: ctx.right_drawer.toggle() if ctx.right_drawer else None,
            ).props("flat round dense").classes("mr-1")

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
            ).props("dense outlined").classes("min-w-[180px] app-input")

            mode_label = "Dark" if is_dark else "Light"
            mode_icon = "dark_mode" if is_dark else "light_mode"

            def on_toggle_theme() -> None:
                cfg_local = get_app_config()
                cfg_local.ui.navigation.dark_mode = not bool(getattr(cfg_local.ui.navigation, "dark_mode", False))
                save_app_config(cfg_local)
                ui.run_javascript("location.reload()")

            ui.button(mode_label, icon=mode_icon, on_click=on_toggle_theme).props("flat no-caps")

            # Live date/time
            dt_label = ui.label("").classes("ml-3 text-sm")

            def update_time() -> None:
                dt_label.set_text(datetime.now().strftime("%d-%m-%Y %H:%M"))

            update_time()
            ui.timer(60.0, update_time)

            # User info (icon + username)
            user = get_user()
            username = user.username if user else "unknown"
            full_name = ""
            if user:
                full_name = ("%s %s" % (user.forename, user.lastname)).strip()

            with ui.row().classes("ml-4 items-center gap-2"):
                ui.icon("account_circle").classes("text-sm")
                with ui.column().classes("gap-0"):
                    username_label = ui.label(username).classes("text-sm")
                    if has_role("admin"):
                        username_label.classes(add="cursor-pointer text-primary")
                        username_label.on("click", lambda: ui.run_javascript("window.location.href = '/?page=settings'"))
                    ui.label(full_name or "-").classes("text-xs text-gray-300")

            # Logout
            def do_logout() -> None:
                if user:
                    ok, detail = unregister_itac_user(user.username)
                    if not ok:
                        ui.notify(f"iTAC unregister failed: {detail}", type="warning")
                logout()
                ui.run_javascript("window.location.href = '/login'")

            ui.button(t("header.logout", "Logout"), icon="logout", on_click=do_logout).props("flat no-caps") \
                .classes("ml-2")

    return header
