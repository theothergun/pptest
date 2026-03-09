from __future__ import annotations

from nicegui import ui


def action_button(label: str, on_click, *, icon: str = "play_arrow", tone: str = "button-primary") -> ui.button:
    btn = ui.button(label, on_click=on_click, icon=icon)
    btn.classes(f"button {tone}")
    btn.props("no-caps")
    return btn


def toolbar() -> ui.row:
    return ui.row().classes("w-full items-center gap-2")
