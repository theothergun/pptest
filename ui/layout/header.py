from __future__ import annotations

from nicegui import ui

from design_system_content import DS


def app_header(title: str, subtitle: str | None = None) -> None:
    with ui.row().classes(DS.page_header_row):
        with ui.column().classes("gap-0"):
            ui.label(title).classes(DS.page_title)
            if subtitle:
                ui.label(subtitle).classes(DS.page_subtitle)
