from __future__ import annotations

from nicegui import ui

from layout.context import PageContext


def render_settings_header(ctx: PageContext, title: str, subtitle: str = "") -> None:
    """Render the shared header used by the settings page."""
    with ui.column().classes("w-full gap-1"):
        ui.label(title).classes("text-2xl font-semibold")
        if subtitle:
            ui.label(subtitle).classes("text-sm text-gray-500")
