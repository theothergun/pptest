from __future__ import annotations

import json
import os
from typing import Any

from nicegui import ui

from layout.main_area import PageContext
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config


def render(container: ui.element, ctx: PageContext) -> None:
    with container:
        ui.label("TCP Clients").classes("text-2xl font-bold")
        ui.label("Configure TCP client worker endpoints.").classes("text-sm text-gray-500")

        clients_container = ui.column().classes("w-full gap-2 mt-4")

        with ui.card().classes("w-full gap-4"):
            ui.label("Add TCP client").classes("text-lg font-semibold")
            client_id = ui.input("Client ID").classes("w-full")
            host = ui.input("Host").classes("w-full")
            port = ui.input("Port").classes("w-full")
            connect = ui.switch("Connect on startup", value=True)
            mode = ui.input("Mode", value="line").classes("w-full")
            delimiter = ui.input("Delimiter", value="\\n").classes("w-full")
            encoding = ui.input("Encoding", value="utf-8").classes("w-full")
            auto_reconnect = ui.switch("Auto reconnect", value=True)
            reconnect_min_s = ui.input("Reconnect min (s)", value="1.0").classes("w-full")
            reconnect_max_s = ui.input("Reconnect max (s)", value="10.0").classes("w-full")
            keepalive = ui.switch("Keepalive", value=True)
            tcp_nodelay = ui.switch("TCP no delay", value=True)

            ui.button(
                "Add client",
                on_click=lambda: _add_client(
                    client_id.value,
                    host.value,
                    port.value,
                    connect.value,
                    mode.value,
                    delimiter.value,
                    encoding.value,
                    auto_reconnect.value,
                    reconnect_min_s.value,
                    reconnect_max_s.value,
                    keepalive.value,
                    tcp_nodelay.value,
                    clients_container,
                ),
            ).props("color=primary")

        ui.separator().classes("my-2")
        ui.label("Existing clients").classes("text-lg font-semibold")
        _render_clients(clients_container)


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


def _get_tcp_clients(data: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        data.get("workers", {})
        .get("configs", {})
        .get("tcp_client", {})
        .get("clients", [])
    )


def _set_tcp_clients(data: dict[str, Any], clients: list[dict[str, Any]]) -> None:
    data.setdefault("workers", {})
    data["workers"].setdefault("configs", {})
    data["workers"]["configs"].setdefault("tcp_client", {})
    data["workers"]["configs"]["tcp_client"]["clients"] = clients


def _render_clients(container: ui.element) -> None:
    container.clear()
    data = _load_config_data()
    clients = _get_tcp_clients(data)

    if not clients:
        ui.label("No TCP clients configured yet.").classes("text-sm text-gray-500")
        return

    for idx, client in enumerate(clients):
        with ui.card().classes("w-full"):
            ui.label(client.get("client_id", "")).classes("font-medium")
            with ui.row().classes("w-full items-center gap-4"):
                host_input = ui.input("Host", value=client.get("host", "")).classes("flex-1")
                port_input = ui.input("Port", value=str(client.get("port", ""))).classes("flex-1")
            connect_input = ui.switch("Connect on startup", value=client.get("connect", True))
            mode_input = ui.input("Mode", value=client.get("mode", "line")).classes("w-full")
            delimiter_input = ui.input("Delimiter", value=client.get("delimiter", "\\n")).classes("w-full")
            encoding_input = ui.input("Encoding", value=client.get("encoding", "utf-8")).classes("w-full")
            auto_reconnect_input = ui.switch("Auto reconnect", value=client.get("auto_reconnect", True))
            reconnect_min_input = ui.input(
                "Reconnect min (s)",
                value=str(client.get("reconnect_min_s", 1.0)),
            ).classes("w-full")
            reconnect_max_input = ui.input(
                "Reconnect max (s)",
                value=str(client.get("reconnect_max_s", 10.0)),
            ).classes("w-full")
            keepalive_input = ui.switch("Keepalive", value=client.get("keepalive", True))
            tcp_nodelay_input = ui.switch("TCP no delay", value=client.get("tcp_nodelay", True))
            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button(
                    "Save",
                    on_click=lambda i=idx, hi=host_input, pi=port_input, ci=connect_input, mi=mode_input,
                    di=delimiter_input, ei=encoding_input, ari=auto_reconnect_input, rmin=reconnect_min_input,
                    rmax=reconnect_max_input, kai=keepalive_input, tni=tcp_nodelay_input: _update_client(
                        i,
                        hi.value,
                        pi.value,
                        ci.value,
                        mi.value,
                        di.value,
                        ei.value,
                        ari.value,
                        rmin.value,
                        rmax.value,
                        kai.value,
                        tni.value,
                        container,
                    ),
                ).props("color=primary")
                ui.button(
                    "Delete",
                    on_click=lambda i=idx: _delete_client(i, container),
                ).props("color=negative flat")


def _add_client(
    client_id: str,
    host: str,
    port: str,
    connect: bool,
    mode: str,
    delimiter: str,
    encoding: str,
    auto_reconnect: bool,
    reconnect_min_s: str,
    reconnect_max_s: str,
    keepalive: bool,
    tcp_nodelay: bool,
    container: ui.element,
) -> None:
    if not client_id or not host or not port:
        ui.notify("Client ID, host, and port are required.", type="negative")
        return
    port_value = _parse_int(port, "Port must be a number.")
    if port_value is None:
        return
    reconnect_min_value = _parse_float(reconnect_min_s, "Reconnect min must be a number.")
    if reconnect_min_value is None:
        return
    reconnect_max_value = _parse_float(reconnect_max_s, "Reconnect max must be a number.")
    if reconnect_max_value is None:
        return

    data = _load_config_data()
    clients = list(_get_tcp_clients(data))
    clients.append(
        {
            "client_id": client_id,
            "host": host,
            "port": port_value,
            "connect": bool(connect),
            "mode": mode or "line",
            "delimiter": delimiter or "\\n",
            "encoding": encoding or "utf-8",
            "auto_reconnect": bool(auto_reconnect),
            "reconnect_min_s": reconnect_min_value,
            "reconnect_max_s": reconnect_max_value,
            "keepalive": bool(keepalive),
            "tcp_nodelay": bool(tcp_nodelay),
        }
    )
    _set_tcp_clients(data, clients)
    _write_config_data(data)
    ui.notify("TCP client added.", type="positive")
    _render_clients(container)


def _delete_client(index: int, container: ui.element) -> None:
    data = _load_config_data()
    clients = list(_get_tcp_clients(data))
    if index < 0 or index >= len(clients):
        ui.notify("Client not found.", type="negative")
        return
    clients.pop(index)
    _set_tcp_clients(data, clients)
    _write_config_data(data)
    ui.notify("TCP client removed.", type="positive")
    _render_clients(container)


def _update_client(
    index: int,
    host: str,
    port: str,
    connect: bool,
    mode: str,
    delimiter: str,
    encoding: str,
    auto_reconnect: bool,
    reconnect_min_s: str,
    reconnect_max_s: str,
    keepalive: bool,
    tcp_nodelay: bool,
    container: ui.element,
) -> None:
    port_value = _parse_int(port, "Port must be a number.")
    if port_value is None:
        return
    reconnect_min_value = _parse_float(reconnect_min_s, "Reconnect min must be a number.")
    if reconnect_min_value is None:
        return
    reconnect_max_value = _parse_float(reconnect_max_s, "Reconnect max must be a number.")
    if reconnect_max_value is None:
        return

    data = _load_config_data()
    clients = list(_get_tcp_clients(data))
    if index < 0 or index >= len(clients):
        ui.notify("Client not found.", type="negative")
        return

    current = clients[index]
    clients[index] = {
        "client_id": current.get("client_id", ""),
        "host": host,
        "port": port_value,
        "connect": bool(connect),
        "mode": mode or "line",
        "delimiter": delimiter or "\\n",
        "encoding": encoding or "utf-8",
        "auto_reconnect": bool(auto_reconnect),
        "reconnect_min_s": reconnect_min_value,
        "reconnect_max_s": reconnect_max_value,
        "keepalive": bool(keepalive),
        "tcp_nodelay": bool(tcp_nodelay),
    }
    _set_tcp_clients(data, clients)
    _write_config_data(data)
    ui.notify("TCP client updated.", type="positive")
    _render_clients(container)


def _parse_int(value: str, message: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        ui.notify(message, type="negative")
        return None


def _parse_float(value: str, message: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        ui.notify(message, type="negative")
        return None
