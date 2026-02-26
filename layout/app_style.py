from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppTokens:
    """Shared NOX packaging style tokens (mapped to CSS variables set by ui_theme)."""

    radius_lg: str = "16px"
    radius_md: str = "12px"
    radius_sm: str = "10px"
    shadow_panel: str = "0 10px 24px rgba(16, 24, 40, 0.08)"
    shadow_shell: str = "0 12px 30px rgba(16, 24, 40, 0.06)"
    spacing_page: str = "16px"


TOKENS = AppTokens()


BUTTON_VARIANTS: dict[str, str] = {
    "primary": "color=primary text-color=white unelevated no-caps",
    "secondary": "color=secondary text-color=white unelevated no-caps",
    "success": "color=positive text-color=white unelevated no-caps",
    "warning": "color=warning text-color=black unelevated no-caps",
    "danger": "color=negative text-color=white unelevated no-caps",
    "neutral": "outline color=secondary no-caps",
}


def button_props(variant: str = "primary") -> str:
    return BUTTON_VARIANTS.get(variant, BUTTON_VARIANTS["primary"])


def button_classes(full: bool = False) -> str:
    base = "app-btn h-[40px] px-4 rounded-xl font-semibold"
    return f"{base} w-full" if full else base


def panel_classes(padded: bool = True) -> str:
    base = "app-panel w-full"
    return f"{base} p-4" if padded else base


def section_title_classes() -> str:
    return "text-base font-semibold text-[var(--text-primary)]"


def section_subtitle_classes() -> str:
    return "text-sm text-[var(--text-secondary)]"
