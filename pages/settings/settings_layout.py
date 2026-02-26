from __future__ import annotations

from nicegui import ui

from layout.context import PageContext


def render_settings_header(ctx: PageContext, title: str, subtitle: str = "") -> None:
    """Render the shared header used by the settings page."""
    _ = ctx
    with ui.column().classes("w-full gap-1 app-panel p-4 mb-2"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("settings").classes("text-primary")
            ui.label(title).classes("text-2xl font-semibold text-[var(--text-primary)]")
        if subtitle:
            ui.label(subtitle).classes("text-sm text-[var(--text-secondary)]")
