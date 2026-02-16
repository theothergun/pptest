from __future__ import annotations

from nicegui import ui

from services.app_config import AppConfig


def _active_palette_name(cfg: AppConfig) -> str:
    theme = cfg.ui.theme
    is_dark = bool(getattr(cfg.ui.navigation, "dark_mode", False))
    return theme.dark_palette if is_dark else theme.light_palette


def get_theme_palette(cfg: AppConfig) -> dict[str, str]:
    theme = cfg.ui.theme
    palette_name = _active_palette_name(cfg)
    palette = theme.palettes.get(palette_name, {})
    return {str(k): str(v) for k, v in palette.items()}


def get_theme_color(cfg: AppConfig, key: str, fallback: str) -> str:
    palette = get_theme_palette(cfg)
    return str(palette.get(key, fallback))


def _css_variables_block(palette: dict[str, str]) -> str:
    rows = []
    for key, value in sorted(palette.items()):
        rows.append(f"--{key}: {value};")
    return "\n".join(rows)


def apply_ui_theme(cfg: AppConfig) -> None:
    palette = get_theme_palette(cfg)

    ui.colors(
        primary=palette.get("primary", "#3b82f6"),
        secondary=palette.get("secondary", "#0ea5e9"),
        accent=palette.get("accent", "#22c55e"),
        positive=palette.get("positive", "#16a34a"),
        negative=palette.get("negative", "#dc2626"),
        warning=palette.get("warning", "#f59e0b"),
        info=palette.get("info", "#0284c7"),
    )
    ui.dark_mode(bool(getattr(cfg.ui.navigation, "dark_mode", False)))

    css_vars = _css_variables_block(palette)
    ui.add_head_html(
        """
        <style>
            :root {
        %s
            }

            html, body, #app, .nicegui-content {
                background-color: var(--app-background);
                color: var(--text-primary);
            }

            .app-header {
                background-color: var(--header-bg) !important;
                color: var(--header-text) !important;
            }

            .app-drawer {
                background-color: var(--drawer-bg) !important;
                color: var(--drawer-text) !important;
            }

            .app-input .q-field__control {
                background-color: var(--input-bg) !important;
                color: var(--input-text) !important;
                border-color: var(--input-border) !important;
            }

            .app-input .q-field__native,
            .app-input .q-field__prefix,
            .app-input .q-field__suffix,
            .app-input .q-field__marginal,
            .app-input .q-field__label,
            .app-input .q-select__dropdown-icon {
                color: var(--input-text) !important;
            }

            .q-menu,
            .q-dialog__inner > div,
            .q-card {
                background-color: var(--surface);
                color: var(--text-primary);
            }

            .app-muted {
                color: var(--text-secondary) !important;
            }

            .text-gray-300,
            .text-gray-400,
            .text-gray-500,
            .text-gray-600,
            .text-gray-700 {
                color: var(--text-secondary) !important;
            }

            .bg-gray-50,
            .bg-gray-100,
            .bg-gray-200 {
                background-color: var(--surface-muted) !important;
            }
        </style>
        """
        % css_vars
    )
