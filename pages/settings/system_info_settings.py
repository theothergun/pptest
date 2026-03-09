from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
from datetime import datetime
from importlib import metadata

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_active_set_name


def _run_cmd(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


def _station_name() -> str:
    env_station = os.environ.get("STATION_NAME", "").strip()
    if env_station:
        return env_station
    return f"Config Set: {get_active_set_name()}"


def _application_version() -> dict[str, str]:
    commit = _run_cmd(["git", "rev-parse", "--short", "HEAD"])
    branch = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    date = _run_cmd(["git", "log", "-1", "--format=%cd", "--date=iso"])
    return {
        "commit": commit or "n/a",
        "branch": branch or "n/a",
        "date": date or "n/a",
    }


def _dns_servers() -> str:
    servers: list[str] = []
    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("nameserver "):
                    servers.append(line.split(maxsplit=1)[1])
    except Exception:
        return "n/a"
    return ", ".join(servers) if servers else "n/a"


def _connection_names() -> dict[str, str]:
    mapping: dict[str, str] = {}
    out = _run_cmd(["nmcli", "-t", "-f", "DEVICE,CONNECTION", "device", "status"])
    if not out:
        return mapping
    for row in out.splitlines():
        if ":" not in row:
            continue
        device, conn = row.split(":", 1)
        mapping[device.strip()] = conn.strip() if conn.strip() and conn.strip() != "--" else "n/a"
    return mapping


def _default_gateways() -> dict[str, str]:
    gateways: dict[str, str] = {}
    out = _run_cmd(["ip", "-j", "route", "show", "default"])
    if not out:
        return gateways
    try:
        routes = json.loads(out)
    except Exception:
        return gateways
    for route in routes:
        dev = str(route.get("dev", "")).strip()
        gw = str(route.get("gateway", "")).strip() or "n/a"
        if dev:
            gateways[dev] = gw
    return gateways


def _network_rows() -> list[dict[str, str]]:
    out = _run_cmd(["ip", "-j", "addr", "show"])
    if not out:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []

    conn_names = _connection_names()
    gateways = _default_gateways()
    dns = _dns_servers()

    rows: list[dict[str, str]] = []
    for iface in data:
        name = str(iface.get("ifname", "")).strip()
        if not name:
            continue

        ipv4s: list[str] = []
        ipv6s: list[str] = []
        for addr in iface.get("addr_info", []):
            family = str(addr.get("family", ""))
            local = str(addr.get("local", "")).strip()
            prefix = addr.get("prefixlen")
            if not local:
                continue
            text = f"{local}/{prefix}" if prefix is not None else local
            if family == "inet":
                ipv4s.append(text)
            elif family == "inet6":
                ipv6s.append(text)

        rows.append(
            {
                "name": name,
                "network_name": conn_names.get(name, "n/a"),
                "ipv4": ", ".join(ipv4s) if ipv4s else "n/a",
                "ipv6": ", ".join(ipv6s) if ipv6s else "n/a",
                "gateway": gateways.get(name, "n/a"),
                "dns": dns,
            }
        )

    return rows


def _python_modules() -> list[dict[str, str]]:
    mods: list[dict[str, str]] = []
    try:
        for dist in metadata.distributions():
            name = dist.metadata.get("Name") or dist.metadata.get("Summary") or "unknown"
            version = dist.version or "n/a"
            mods.append({"name": str(name), "version": str(version)})
    except Exception:
        return []
    mods.sort(key=lambda x: x["name"].lower())
    return mods


def render(container: ui.element, _ctx: PageContext) -> None:
    station_name = _station_name()
    computer_name = socket.gethostname()
    app_version = _application_version()
    net_rows = _network_rows()
    py_modules = _python_modules()

    with container.classes("w-full"):
        with ui.card().classes("w-full"):
            ui.label("Station & System Overview").classes("text-xl font-semibold")
            ui.label("Single-page overview of station identity, network details, and runtime versions.").classes(
                "text-sm text-gray-500"
            )

            ui.separator().classes("my-2")
            ui.label("Identity").classes("text-lg font-semibold")
            with ui.row().classes("w-full gap-3"):
                ui.input("Station name", value=station_name).props("readonly outlined").classes("w-full")
                ui.input("Computer name", value=computer_name).props("readonly outlined").classes("w-full")

            ui.separator().classes("my-2")
            ui.label("Application Version").classes("text-lg font-semibold")
            with ui.row().classes("w-full gap-3"):
                ui.input("Git commit", value=app_version["commit"]).props("readonly outlined").classes("w-full")
                ui.input("Git branch", value=app_version["branch"]).props("readonly outlined").classes("w-full")
                ui.input("Last commit date", value=app_version["date"]).props("readonly outlined").classes("w-full")

            ui.separator().classes("my-2")
            ui.label("Python Runtime").classes("text-lg font-semibold")
            with ui.row().classes("w-full gap-3"):
                ui.input("Python version", value=platform.python_version()).props("readonly outlined").classes("w-full")
                ui.input("Module count", value=str(len(py_modules))).props("readonly outlined").classes("w-full")
                ui.input("Generated at", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S")).props("readonly outlined").classes("w-full")

            with ui.expansion("Installed Python modules", icon="inventory_2").classes("w-full"):
                if py_modules:
                    ui.table(
                        columns=[
                            {"name": "name", "label": "Module", "field": "name", "align": "left"},
                            {"name": "version", "label": "Version", "field": "version", "align": "left"},
                        ],
                        rows=py_modules,
                        row_key="name",
                        pagination=30,
                    ).classes("w-full")
                else:
                    ui.label("Module list unavailable in this environment.").classes("text-sm text-gray-500")

            ui.separator().classes("my-2")
            ui.label("Network Interfaces").classes("text-lg font-semibold")
            if net_rows:
                ui.table(
                    columns=[
                        {"name": "name", "label": "Interface", "field": "name", "align": "left"},
                        {"name": "network_name", "label": "Network name", "field": "network_name", "align": "left"},
                        {"name": "ipv4", "label": "IPv4", "field": "ipv4", "align": "left"},
                        {"name": "ipv6", "label": "IPv6", "field": "ipv6", "align": "left"},
                        {"name": "gateway", "label": "Gateway", "field": "gateway", "align": "left"},
                        {"name": "dns", "label": "DNS", "field": "dns", "align": "left"},
                    ],
                    rows=net_rows,
                    row_key="name",
                    pagination=20,
                ).classes("w-full")
            else:
                ui.label("No interface details available (missing OS tools or permissions). ").classes(
                    "text-sm text-gray-500"
                )
