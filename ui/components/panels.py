from __future__ import annotations

from nicegui import ui

from design_system_content import DS


def page_container() -> ui.column:
    return ui.column().classes(DS.page_container)


def panel(title: str, subtitle: str | None = None, *, icon: str = "ti-layout-grid") -> ui.card:
    card = ui.card().classes(DS.panel)
    with card:
        with ui.row().classes(DS.page_header_row):
            with ui.row().classes("items-center gap-2"):
                ui.html(f'<i class="{DS.icon} {icon}"></i>').classes("text-base")
                ui.label(title).classes("section-title")
            if subtitle:
                ui.label(subtitle).classes("text-sm text-muted")
    return card


def card(title: str | None = None) -> ui.card:
    c = ui.card().classes(DS.card)
    if title:
        with c:
            ui.label(title).classes("text-base font-semi")
    return c
