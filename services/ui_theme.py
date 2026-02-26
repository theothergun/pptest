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

            .app-shell {
                background: linear-gradient(135deg, var(--surface-muted) 0%, var(--app-background) 100%);
                border-radius: 20px;
                border: 1px solid var(--input-border);
                box-shadow: 0 12px 30px rgba(16, 24, 40, 0.06);
            }

            .app-panel {
                background: var(--surface);
                border: 1px solid var(--input-border);
                border-radius: 16px;
                box-shadow: 0 10px 24px rgba(16, 24, 40, 0.08);
                color: var(--text-primary);
            }

            .app-btn {
                font-weight: 700;
                letter-spacing: .2px;
                border-radius: 12px;
                transition: transform 120ms ease, box-shadow 120ms ease;
            }

            .app-btn:hover { transform: translateY(-1px); box-shadow: 0 10px 20px rgba(15, 23, 42, 0.12); }

            .app-btn.q-btn--disabled,
            .app-btn.q-btn--disabled:hover {
                background-color: #9ca3af !important;
                border-color: #6b7280 !important;
                color: #374151 !important;
                opacity: 1 !important;
                box-shadow: none !important;
                transform: none !important;
            }

            .app-nav-item {
                border-radius: 12px;
                justify-content: flex-start;
                min-height: 42px;
                font-weight: 600;
            }

            .app-nav-item.q-btn--active,
            .app-nav-item.app-nav-item-active {
                background: var(--primary) !important;
                color: #ffffff !important;
            }

            .app-header-title { font-size: 1.05rem; font-weight: 700; letter-spacing: .2px; }
            .app-muted { color: var(--text-secondary); }

            .q-notification {
                border: 1px solid var(--input-border);
                border-radius: 12px;
                box-shadow: 0 10px 20px rgba(16, 24, 40, 0.18);
            }
        </style>
        """
        % css_vars
    )
