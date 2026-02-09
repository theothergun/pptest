from __future__ import annotations

import json
import os
from typing import Any

from nicegui import ui

from layout.main_area import PageContext
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config


def render(container: ui.element, ctx: PageContext) -> None:
    with container:
        ui.label("REST API").classes("text-2xl font-bold")
        ui.label("Configure REST API worker endpoints.").classes("text-sm text-gray-500")

        endpoints_container = ui.column().classes("w-full gap-2 mt-4")

        with ui.card().classes("w-full gap-4"):
            ui.label("Add REST endpoint").classes("text-lg font-semibold")
            name_input = ui.input("Name").classes("w-full")
            base_url_input = ui.input("Base URL").classes("w-full")
            headers_input = ui.textarea("Headers (JSON)").classes("w-full")
            timeout_input = ui.input("Timeout (s)", value="10").classes("w-full")
            verify_ssl_input = ui.switch("Verify SSL", value=True)

            ui.button(
                "Add endpoint",
                on_click=lambda: _add_endpoint(
                    name_input.value,
                    base_url_input.value,
                    headers_input.value,
                    timeout_input.value,
                    verify_ssl_input.value,
                    endpoints_container,
                ),
            ).props("color=primary")

        ui.separator().classes("my-2")
        ui.label("Existing endpoints").classes("text-lg font-semibold")
        _render_endpoints(endpoints_container)


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


def _get_endpoints(data: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        data.get("workers", {})
        .get("configs", {})
        .get("rest_api", {})
        .get("endpoints", [])
    )


def _set_endpoints(data: dict[str, Any], endpoints: list[dict[str, Any]]) -> None:
    data.setdefault("workers", {})
    data["workers"].setdefault("configs", {})
    data["workers"]["configs"].setdefault("rest_api", {})
    data["workers"]["configs"]["rest_api"]["endpoints"] = endpoints


def _render_endpoints(container: ui.element) -> None:
    container.clear()
    data = _load_config_data()
    endpoints = _get_endpoints(data)

    if not endpoints:
        ui.label("No REST API endpoints configured yet.").classes("text-sm text-gray-500")
        return

    for idx, endpoint in enumerate(endpoints):
        with ui.card().classes("w-full"):
            ui.label(endpoint.get("name", "")).classes("font-medium")
            name_input = ui.input("Name", value=endpoint.get("name", "")).classes("w-full")
            base_url_input = ui.input("Base URL", value=endpoint.get("base_url", "")).classes("w-full")
            headers_input = ui.textarea(
                "Headers (JSON)",
                value=json.dumps(endpoint.get("headers", {}), indent=2),
            ).classes("w-full")
            timeout_input = ui.input(
                "Timeout (s)",
                value=str(endpoint.get("timeout_s", 10.0)),
            ).classes("w-full")
            verify_ssl_input = ui.switch("Verify SSL", value=endpoint.get("verify_ssl", True))
            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button(
                    "Save",
                    on_click=lambda i=idx, ni=name_input, bi=base_url_input, hi=headers_input,
                    ti=timeout_input, vi=verify_ssl_input: _update_endpoint(
                        i,
                        ni.value,
                        bi.value,
                        hi.value,
                        ti.value,
                        vi.value,
                        container,
                    ),
                ).props("color=primary")
                ui.button(
                    "Delete",
                    on_click=lambda i=idx: _delete_endpoint(i, container),
                ).props("color=negative flat")


def _add_endpoint(
    name: str,
    base_url: str,
    headers_raw: str,
    timeout_s: str,
    verify_ssl: bool,
    container: ui.element,
) -> None:
    if not name or not base_url:
        ui.notify("Name and base URL are required.", type="negative")
        return
    headers = _parse_headers(headers_raw)
    if headers is None:
        return
    timeout_value = _parse_float(timeout_s, "Timeout must be a number.")
    if timeout_value is None:
        return

    data = _load_config_data()
    endpoints = list(_get_endpoints(data))
    endpoints.append(
        {
            "name": name,
            "base_url": base_url,
            "headers": headers,
            "timeout_s": timeout_value,
            "verify_ssl": bool(verify_ssl),
        }
    )
    _set_endpoints(data, endpoints)
    _write_config_data(data)
    ui.notify("REST endpoint added.", type="positive")
    _render_endpoints(container)


def _delete_endpoint(index: int, container: ui.element) -> None:
    data = _load_config_data()
    endpoints = list(_get_endpoints(data))
    if index < 0 or index >= len(endpoints):
        ui.notify("Endpoint not found.", type="negative")
        return
    endpoints.pop(index)
    _set_endpoints(data, endpoints)
    _write_config_data(data)
    ui.notify("REST endpoint removed.", type="positive")
    _render_endpoints(container)


def _update_endpoint(
    index: int,
    name: str,
    base_url: str,
    headers_raw: str,
    timeout_s: str,
    verify_ssl: bool,
    container: ui.element,
) -> None:
    headers = _parse_headers(headers_raw)
    if headers is None:
        return
    timeout_value = _parse_float(timeout_s, "Timeout must be a number.")
    if timeout_value is None:
        return

    data = _load_config_data()
    endpoints = list(_get_endpoints(data))
    if index < 0 or index >= len(endpoints):
        ui.notify("Endpoint not found.", type="negative")
        return

    endpoints[index] = {
        "name": name,
        "base_url": base_url,
        "headers": headers,
        "timeout_s": timeout_value,
        "verify_ssl": bool(verify_ssl),
    }
    _set_endpoints(data, endpoints)
    _write_config_data(data)
    ui.notify("REST endpoint updated.", type="positive")
    _render_endpoints(container)


def _parse_headers(value: str) -> dict[str, Any] | None:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        ui.notify("Headers must be valid JSON.", type="negative")
        return None
    if not isinstance(parsed, dict):
        ui.notify("Headers JSON must be an object.", type="negative")
        return None
    return parsed


def _parse_float(value: str, message: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        ui.notify(message, type="negative")
        return None
