from __future__ import annotations

"""Design system tokens and reusable class presets.

This module is the single source of truth for layout and component class names.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignSystem:
    page_shell: str = "w-full h-full min-h-0 min-w-0"
    page_container: str = "w-full h-full min-h-0 p-4 gap-3"
    page_header_row: str = "w-full items-center justify-between"
    page_title: str = "page-title"
    page_subtitle: str = "text-sm text-muted"
    panel: str = "w-full app-panel p-4 gap-3"
    card: str = "w-full app-panel p-3 gap-2"
    toolbar: str = "w-full items-center gap-2"
    form_field: str = "w-full"
    table_box: str = "w-full app-panel p-2"
    icon: str = "ti"


DS = DesignSystem()
