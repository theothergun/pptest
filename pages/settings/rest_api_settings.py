from __future__ import annotations

import json
import os
from typing import Any, Callable

from nicegui import ui

from layout.main_area import PageContext
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config

REST_ENDPOINTS_LIST = ExpandableList(
    scroller_id="rest-endpoints-scroll",
    id_prefix="rest-endpoint-card",
    expanded_storage_key="rest_endpoint_expanded_name",
    get_key=lambda ep: str(ep.get("name", "")),
)


def render(container: ui.element, ctx: PageContext) -> None:
    with container.classes("w-full h-full min-h-0 overflow-hidden"):
        with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col"):
            with ui.column().classes("w-full shrink-0 z-10"):
                ui.label("REST API").classes("text-2xl font-bold")
                ui.label("Configure REST API worker endpoints.").classes("text-sm text-gray-500")

            # One shared scroller for add-form + existing entries avoids
            # squeezing the entries area to zero height on small viewports.
            with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto overflow-x-hidden gap-2 p-2 pl-1") as endpoints_scroll:
                endpoints_scroll.props(f"id={REST_ENDPOINTS_LIST.scroller_id}")
                with ui.card().classes("w-full gap-4 mt-2 shrink-0"):
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
                        ),
                    ).props("color=primary")

                ui.separator().classes("my-2 shrink-0")
                ui.label("Existing endpoints").classes("text-lg font-semibold shrink-0")
                _render_endpoints()


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


@ui.refreshable
def _render_endpoints(scroll_to: str | None = None, highlight: str | None = None) -> None:
    data = _load_config_data()
    endpoints = list(_get_endpoints(data))

    if not endpoints:
        ui.label("No REST API endpoints configured yet.").classes("text-sm text-gray-500")
        return

    def refresh() -> None:
        _render_endpoints.refresh(scroll_to=None, highlight=None)

    def render_summary(endpoint: dict[str, Any], idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        timeout_s = endpoint.get("timeout_s", 10.0)
        verify_ssl = bool(endpoint.get("verify_ssl", True))
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3 min-w-0"):
                ui.label(str(endpoint.get("name", ""))).classes("font-medium")
                ui.label(str(endpoint.get("base_url", ""))).classes("text-xs text-gray-500 truncate")
                ui.label(f"timeout={timeout_s}s").classes("text-xs text-gray-400")
                ui.label("SSL on" if verify_ssl else "SSL off").classes("text-xs text-gray-400")
            with ui.row().classes("items-center gap-2 shrink-0"):
                ui.button("Edit", on_click=toggle).props("flat color=primary")
                ui.button("Delete", on_click=delete).props("flat color=negative")

    def render_editor(endpoint: dict[str, Any], idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-3"):
            ui.label(str(endpoint.get("name", ""))).classes("font-medium")
            ui.button(icon="close", on_click=toggle).props("dense flat round")

        with ui.column().classes("w-full gap-2"):
            name_input = ui.input("Name", value=endpoint.get("name", "")).classes("w-full")
            base_url_input = ui.input("Base URL", value=endpoint.get("base_url", "")).classes("w-full")
            headers_input = ui.textarea(
                "Headers (JSON)",
                value=json.dumps(endpoint.get("headers", {}), indent=2),
            ).classes("w-full")
            timeout_input = ui.input("Timeout (s)", value=str(endpoint.get("timeout_s", 10.0))).classes("w-full")
            verify_ssl_input = ui.switch("Verify SSL", value=endpoint.get("verify_ssl", True))
            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button(
                    "Save",
                    on_click=lambda i=idx, ni=name_input, bi=base_url_input, hi=headers_input, ti=timeout_input, vi=verify_ssl_input: _update_endpoint(
                        i,
                        ni.value,
                        bi.value,
                        hi.value,
                        ti.value,
                        vi.value,
                    ),
                ).props("color=primary")
                ui.button("Delete", on_click=delete).props("color=negative flat")

    REST_ENDPOINTS_LIST.render(
        endpoints,
        render_summary=render_summary,
        render_editor=render_editor,
        on_delete=_delete_endpoint,
        refresh=refresh,
        scroll_to=scroll_to,
        highlight=highlight,
    )


def _add_endpoint(
    name: str,
    base_url: str,
    headers_raw: str,
    timeout_s: str,
    verify_ssl: bool,
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
    endpoint_name = str(name).strip()
    endpoints.append(
        {
            "name": endpoint_name,
            "base_url": base_url,
            "headers": headers,
            "timeout_s": timeout_value,
            "verify_ssl": bool(verify_ssl),
        }
    )
    _set_endpoints(data, endpoints)
    _write_config_data(data)
    ui.notify("REST endpoint added.", type="positive")
    wrapper_id = generate_wrapper_id(REST_ENDPOINTS_LIST.id_prefix, endpoint_name)
    _render_endpoints.refresh(scroll_to=wrapper_id, highlight=wrapper_id)


def _delete_endpoint(index: int) -> None:
    data = _load_config_data()
    endpoints = list(_get_endpoints(data))
    if index < 0 or index >= len(endpoints):
        ui.notify("Endpoint not found.", type="negative")
        return
    endpoints.pop(index)
    _set_endpoints(data, endpoints)
    _write_config_data(data)
    ui.notify("REST endpoint removed.", type="positive")
    _render_endpoints.refresh(scroll_to=None, highlight=None)


def _update_endpoint(
    index: int,
    name: str,
    base_url: str,
    headers_raw: str,
    timeout_s: str,
    verify_ssl: bool,
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
    if index < 0 or index >= len(endpoints):
        ui.notify("Endpoint not found.", type="negative")
        return

    endpoints[index] = {
        "name": str(name).strip(),
        "base_url": base_url,
        "headers": headers,
        "timeout_s": timeout_value,
        "verify_ssl": bool(verify_ssl),
    }
    _set_endpoints(data, endpoints)
    _write_config_data(data)
    ui.notify("REST endpoint updated.", type="positive")
    _render_endpoints.refresh(scroll_to=None, highlight=None)


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
