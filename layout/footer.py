from nicegui import ui


def build_footer() -> ui.footer:
    footer = ui.footer().classes("h-12 w-full")

    with footer:
        with ui.row().classes("h-full items-center w-full px-4"):
            ui.label("© 2026 My App").classes("text-sm")
            ui.space()
            ui.label("Multi-user safe").classes("text-sm text-gray-300")

    return footer
