from nicegui import ui
from services.i18n import t


def build_footer() -> ui.footer:
    footer = ui.footer().classes("h-12 w-full")

    with footer:
        with ui.row().classes("h-full items-center w-full px-4"):
            ui.label(t("footer.copyright", "© 2026 My App")).classes("text-sm")
            ui.space()
            ui.label(t("footer.multi_user_safe", "Multi-user safe")).classes("text-sm text-gray-300")

    return footer
