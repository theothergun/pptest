from __future__ import annotations

from nicegui import ui


def notify(message: str, *, tone: str = "positive") -> None:
    ui.notify(message, type=tone, classes="app-notification")
