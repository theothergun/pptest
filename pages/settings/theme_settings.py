from __future__ import annotations

import re

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_app_config, save_app_config


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")

COLOR_KEYS = [
    "primary",
    "secondary",
    "accent",
    "positive",
    "negative",
    "warning",
    "info",
    "app-background",
    "surface",
    "surface-muted",
    "text-primary",
    "text-secondary",
    "header-bg",
    "header-text",
    "drawer-bg",
    "drawer-text",
    "input-bg",
    "input-text",
    "input-border",
    "status-good",
    "status-warning",
    "status-bad",
    "status-info",
    "status-muted",
]


def render(container: ui.element, _ctx: PageContext) -> None:
    with container.classes("w-full"):
        cfg = get_app_config()
        palettes = cfg.ui.theme.palettes

        with ui.card().classes("w-full"):
            ui.label("Color Themes").classes("text-xl font-semibold")
            ui.label("Edit the light-cool and dark-cool palettes.").classes("text-sm app-muted")

            inputs: dict[tuple[str, str], ui.input] = {}
            previews: dict[tuple[str, str], ui.element] = {}

            def _build_palette_editor(palette_name: str) -> None:
                palette = palettes.get(palette_name, {})
                with ui.column().classes("w-full gap-2"):
                    for key in COLOR_KEYS:
                        value = str(palette.get(key, "#000000"))
                        with ui.row().classes("w-full items-center gap-3"):
                            ui.label(key).classes("w-[180px] text-sm")
                            color_input = ui.input(value=value).props("dense outlined").classes("w-[180px] app-input")
                            color_picker = ui.input(value=value).props("type=color").classes("w-[48px] p-0")
                            preview = ui.element("div").classes("w-8 h-8 rounded border")
                            preview.style("background-color: %s;" % value)

                            def _update_preview(e, p=preview):
                                p.style("background-color: %s;" % str(getattr(e, "value", "") or "transparent"))

                            def _sync_from_text(e, p=preview, picker=color_picker):
                                val = str(getattr(e, "value", "") or "").strip()
                                _update_preview(e, p)
                                if _HEX_COLOR_RE.match(val):
                                    try:
                                        picker.value = val
                                    except Exception:
                                        pass

                            def _sync_from_picker(e, text_input=color_input, p=preview):
                                val = str(getattr(e, "value", "") or "").strip()
                                if val:
                                    try:
                                        text_input.value = val
                                    except Exception:
                                        pass
                                _update_preview(e, p)

                            color_input.on_value_change(_sync_from_text)
                            color_picker.on_value_change(_sync_from_picker)
                            inputs[(palette_name, key)] = color_input
                            previews[(palette_name, key)] = preview

            with ui.tabs().classes("w-full") as tabs:
                ui.tab("light-cool")
                ui.tab("dark-cool")

            with ui.tab_panels(tabs, value="light-cool").classes("w-full"):
                with ui.tab_panel("light-cool"):
                    _build_palette_editor("light-cool")
                with ui.tab_panel("dark-cool"):
                    _build_palette_editor("dark-cool")

            def save_theme() -> None:
                cfg_local = get_app_config()
                for palette_name in ("light-cool", "dark-cool"):
                    cfg_local.ui.theme.palettes.setdefault(palette_name, {})
                    for key in COLOR_KEYS:
                        raw_value = str(inputs[(palette_name, key)].value or "").strip()
                        if not _HEX_COLOR_RE.match(raw_value):
                            ui.notify(f"Invalid color for {palette_name}.{key}: {raw_value}", type="negative")
                            return
                        cfg_local.ui.theme.palettes[palette_name][key] = raw_value

                save_app_config(cfg_local)
                ui.notify("Color themes saved.", type="positive")
                ui.run_javascript("location.reload()")

            with ui.row().classes("w-full justify-end mt-2"):
                ui.button("Save color themes", on_click=save_theme).props("color=primary")
