from __future__ import annotations

from typing import Any
from nicegui import ui


def table_container(columns: list[dict[str, Any]], rows: list[dict[str, Any]], *, row_key: str) -> ui.table:
    return ui.table(columns=columns, rows=rows, row_key=row_key).props("dense flat bordered").classes("w-full")
