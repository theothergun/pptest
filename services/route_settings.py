from __future__ import annotations

from typing import Any

from services.app_config import get_app_config, save_app_config


def get_route_settings(route_key: str) -> dict[str, Any]:
    cfg = get_app_config()
    nav = cfg.ui.navigation
    settings = dict((nav.route_settings or {}).get(route_key, {}) or {})
    return settings


def set_route_settings(route_key: str, settings: dict[str, Any]) -> None:
    cfg = get_app_config()
    nav = cfg.ui.navigation
    nav.route_settings[route_key] = dict(settings)
    save_app_config(cfg)
