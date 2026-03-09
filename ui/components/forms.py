from __future__ import annotations

from nicegui import ui


def form_field(label: str, value: str = "") -> ui.input:
    return ui.input(label=label, value=value).props("outlined dense").classes("w-full")
