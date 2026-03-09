from __future__ import annotations

from nicegui import ui


CARD_CLASSES = "w-full app-panel"
MUTED_TEXT = "text-sm text-[var(--text-secondary)]"


def section_card(title: str, subtitle: str | None = None, *, icon: str | None = None) -> ui.card:
    card = ui.card().classes(f"{CARD_CLASSES} p-4 gap-3")
    with card:
        with ui.row().classes("w-full items-start gap-3"):
            if icon:
                ui.icon(icon).classes("text-2xl text-primary")
            with ui.column().classes("gap-1"):
                ui.label(title).classes("text-lg font-semibold text-[var(--text-primary)]")
                if subtitle:
                    ui.label(subtitle).classes(MUTED_TEXT)
    return card


def status_badge(text: str, status: str = "info") -> ui.badge:
    color_map = {
        "ok": "positive",
        "warning": "warning",
        "error": "negative",
        "info": "primary",
        "muted": "grey-7",
    }
    return ui.badge(text, color=color_map.get(status, "primary")).classes("text-xs")


def kpi_tile(label: str, value: str, *, hint: str | None = None, icon: str | None = None) -> ui.card:
    card = ui.card().classes("w-full min-w-[180px] p-4 gap-2")
    with card:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(label).classes("text-sm text-[var(--text-secondary)]")
            if icon:
                ui.icon(icon).classes("text-primary")
        ui.label(value).classes("text-2xl font-bold text-[var(--text-primary)]")
        if hint:
            ui.label(hint).classes(MUTED_TEXT)
    return card


def action_hint(title: str, lines: list[str]) -> ui.card:
    card = ui.card().classes("w-full p-4 gap-2")
    with card:
        ui.label(title).classes("text-base font-semibold")
        for line in lines:
            ui.label(line).classes(MUTED_TEXT)
    return card
