from __future__ import annotations

import json
import os
from typing import Any

from nicegui import ui

from layout.main_area import PageContext
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config


def render(container: ui.element, ctx: PageContext) -> None:
    with container:
        ui.label("Route Settings").classes("text-2xl font-bold")
        ui.label("Add custom routes (including subfolders like packaging/packaging.py).").classes(
            "text-sm text-gray-500"
        )

        routes_container = ui.column().classes("w-full gap-2 mt-4")

        with ui.card().classes("w-full gap-4"):
            ui.label("Add route").classes("text-lg font-semibold")
            key_input = ui.input("Route key (e.g. packaging)").classes("w-full")
            label_input = ui.input("Label").classes("w-full")
            icon_input = ui.input("Icon (material icon name)").classes("w-full").props("placeholder=settings")
            path_input = ui.input("File path (e.g. packaging/packaging.py)").classes("w-full")
            roles_input = ui.input("Allowed roles (comma separated)").classes("w-full")

            ui.button(
                "Add route",
                on_click=lambda: _add_route(
                    key_input.value,
                    label_input.value,
                    icon_input.value,
                    path_input.value,
                    roles_input.value,
                    routes_container,
                ),
            ).props("color=primary")

        ui.separator().classes("my-2")
        ui.label("Existing custom routes").classes("text-lg font-semibold")
        _render_routes(routes_container)


def _load_config_data() -> dict[str, Any]:
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        cfg = load_app_config(DEFAULT_CONFIG_PATH)
        save_app_config(cfg, DEFAULT_CONFIG_PATH)
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_config_data(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(DEFAULT_CONFIG_PATH), exist_ok=True)
    with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _get_custom_routes(data: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        data.get("ui", {})
        .get("navigation", {})
        .get("custom_routes", [])
    )


def _set_custom_routes(data: dict[str, Any], routes: list[dict[str, Any]]) -> None:
    data.setdefault("ui", {})
    data["ui"].setdefault("navigation", {})
    data["ui"]["navigation"]["custom_routes"] = routes


def _set_route_roles(data: dict[str, Any], route_key: str, roles: list[str]) -> None:
    data.setdefault("ui", {})
    nav = data["ui"].setdefault("navigation", {})
    role_map = nav.setdefault("route_roles", {})
    if roles:
        role_map[route_key] = roles
    else:
        role_map.pop(route_key, None)


def _ensure_visible_route(data: dict[str, Any], route_key: str) -> None:
    nav = data.setdefault("ui", {}).setdefault("navigation", {})
    visible = nav.setdefault("visible_routes", [])
    if route_key not in visible:
        visible.append(route_key)


def _render_routes(container: ui.element) -> None:
    container.clear()
    data = _load_config_data()
    routes = _get_custom_routes(data)

    if not routes:
        ui.label("No custom routes configured yet.").classes("text-sm text-gray-500")
        return

    for idx, route in enumerate(routes):
        roles = (
            data.get("ui", {})
            .get("navigation", {})
            .get("route_roles", {})
            .get(route.get("key", ""), [])
        )
        with ui.card().classes("w-full"):
            ui.label(route.get("key", "")).classes("font-medium")
            with ui.row().classes("w-full items-center gap-4"):
                label_input = ui.input("Label", value=route.get("label", "")).classes("flex-1")
                icon_input = ui.input("Icon", value=route.get("icon", "")).classes("flex-1")
            path_input = ui.input("File path", value=route.get("path", "")).classes("w-full")
            roles_input = ui.input(
                "Allowed roles (comma separated)",
                value=", ".join(roles),
            ).classes("w-full")
            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button(
                    "Save",
                    on_click=lambda i=idx, li=label_input, ii=icon_input, pi=path_input, ri=roles_input: _update_route(
                        i,
                        li.value,
                        ii.value,
                        pi.value,
                        ri.value,
                        container,
                    ),
                ).props("color=primary")
                ui.button(
                    "Delete",
                    on_click=lambda i=idx: _delete_route(i, container),
                ).props("color=negative flat")


def _add_route(
    key: str,
    label: str,
    icon: str,
    path: str,
    roles: str,
    container: ui.element,
) -> None:
    if not key or not path:
        ui.notify("Route key and file path are required.", type="negative")
        return

    data = _load_config_data()
    routes = list(_get_custom_routes(data))
    routes.append(
        {
            "key": key,
            "label": label or key,
            "icon": icon or "insert_drive_file",
            "path": path,
        }
    )
    _set_custom_routes(data, routes)
    role_list = [role.strip() for role in (roles or "").split(",") if role.strip()]
    _set_route_roles(data, key, role_list)
    _ensure_visible_route(data, key)
    _write_config_data(data)
    ui.notify("Route added.", type="positive")
    _render_routes(container)


def _delete_route(index: int, container: ui.element) -> None:
    data = _load_config_data()
    routes = list(_get_custom_routes(data))
    if index < 0 or index >= len(routes):
        ui.notify("Route not found.", type="negative")
        return
    removed = routes.pop(index)
    _set_custom_routes(data, routes)
    if removed.get("key"):
        _set_route_roles(data, removed["key"], [])
    _write_config_data(data)
    ui.notify("Route removed.", type="positive")
    _render_routes(container)


def _update_route(
    index: int,
    label: str,
    icon: str,
    path: str,
    roles: str,
    container: ui.element,
) -> None:
    if not path:
        ui.notify("File path is required.", type="negative")
        return

    data = _load_config_data()
    routes = list(_get_custom_routes(data))
    if index < 0 or index >= len(routes):
        ui.notify("Route not found.", type="negative")
        return

    current = routes[index]
    key = current.get("key", "")
    routes[index] = {
        "key": key,
        "label": label or key,
        "icon": icon or "insert_drive_file",
        "path": path,
    }
    _set_custom_routes(data, routes)
    role_list = [role.strip() for role in (roles or "").split(",") if role.strip()]
    _set_route_roles(data, key, role_list)
    _write_config_data(data)
    ui.notify("Route updated.", type="positive")
    _render_routes(container)
