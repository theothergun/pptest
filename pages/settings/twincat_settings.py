from __future__ import annotations

import json
from typing import Any, Callable

from nicegui import ui

from layout.context import PageContext
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import get_app_config, save_app_config

TWINCAT_LIST = ExpandableList(
    scroller_id="twincat-scroll",
    id_prefix="twincat-card",
    expanded_storage_key="twincat_expanded_client_id",
    get_key=lambda ep: ep.get("client_id", ""),
)


def _parse_int(value: str, message: str) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        ui.notify(message, type="negative")
        return None


def _parse_subscriptions(value: str) -> list[dict[str, Any]] | None:
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        ui.notify("Subscriptions must be valid JSON.", type="negative")
        return None
    if not isinstance(parsed, list):
        ui.notify("Subscriptions JSON must be a list.", type="negative")
        return None
    for item in parsed:
        if not isinstance(item, dict):
            ui.notify("Each subscription item must be an object.", type="negative")
            return None
    return parsed


def render(container: ui.element, _ctx: PageContext) -> None:
    with container.classes("w-full h-full min-h-0 overflow-hidden"):
        with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("TwinCAT").classes("text-2xl font-bold")
                ui.button("Add PLC", on_click=_open_add_dialog).props("color=primary")
            ui.label("Configure TwinCAT PLC endpoints.").classes("text-sm text-gray-500")

            with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-3 p-2") as scroller:
                scroller.props(f"id={TWINCAT_LIST.scroller_id}")
                _render_endpoints()


@ui.refreshable
def _render_endpoints(scroll_to: str | None = None, highlight: str | None = None) -> None:
    cfg = get_app_config()
    tw_cfg = cfg.workers.configs.setdefault("twincat", {})
    endpoints = list(tw_cfg.get("plc_endpoints", []))

    if not endpoints:
        ui.label("No TwinCAT PLC endpoints configured yet.").classes("text-sm text-gray-500")
        return

    def refresh() -> None:
        _render_endpoints.refresh(scroll_to=None, highlight=None)

    def render_summary(ep: dict, _idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3 min-w-0"):
                ui.label(ep.get("client_id", "")).classes("font-medium")
                ui.label(ep.get("plc_ip", "")).classes("text-xs text-gray-500")
                ui.label(f"ADS {ep.get('ads_port', 851)}").classes("text-xs text-gray-400")
            with ui.row().classes("items-center gap-2 shrink-0"):
                ui.button("Edit", on_click=toggle).props("flat color=primary")
                ui.button("Delete", on_click=delete).props("flat color=negative")

    def render_editor(ep: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-2"):
            ui.input("Client ID", value=ep.get("client_id", "")).props("readonly borderless").classes("flex-1")
            ui.button("Close", on_click=toggle).props("flat")

        with ui.row().classes("w-full gap-3"):
            plc_ip = ui.input("PLC IP", value=ep.get("plc_ip", "")).classes("flex-1")
            ams = ui.input("AMS Net ID", value=ep.get("plc_ams_net_id", "")).classes("flex-1")
            ads_port = ui.input("ADS Port", value=str(ep.get("ads_port", 851))).classes("w-40")

        with ui.row().classes("w-full gap-3"):
            trans_mode = ui.input("Default trans mode", value=ep.get("default_trans_mode", "server_cycle")).classes("flex-1")
            cycle_ms = ui.input("Default cycle (ms)", value=str(ep.get("default_cycle_ms", 200))).classes("w-52")
            str_len = ui.input("Default string len", value=str(ep.get("default_string_len", 80))).classes("w-52")

        subs = ui.textarea(
            "Subscriptions (JSON list: [{\"name\":\"Main.CURRENTIP\",\"alias\":\"CurrentIp\",\"plc_type\":\"STRING\",\"string_len\":64}])",
            value=json.dumps(ep.get("subscriptions", []), indent=2),
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                "Save",
                on_click=lambda i=idx, cid=ep.get("client_id", ""), ip=plc_ip, net=ams, ap=ads_port, tm=trans_mode, cm=cycle_ms, sl=str_len, su=subs:
                _update_endpoint(i, cid, ip.value, net.value, ap.value, tm.value, cm.value, sl.value, su.value),
            ).props("color=primary")
            ui.button("Delete", on_click=delete).props("flat color=negative")

    TWINCAT_LIST.render(
        endpoints,
        render_summary=render_summary,
        render_editor=render_editor,
        on_delete=_delete_endpoint,
        refresh=refresh,
        scroll_to=scroll_to,
        highlight=highlight,
    )


def _open_add_dialog() -> None:
    d = ui.dialog()
    with d, ui.card().classes("w-[900px] max-w-[95vw]"):
        ui.label("Add TwinCAT PLC").classes("text-lg font-semibold")
        client_id = ui.input("Client ID").classes("w-full")
        plc_ip = ui.input("PLC IP").classes("w-full")
        ams = ui.input("AMS Net ID").classes("w-full")
        ads_port = ui.input("ADS Port", value="851").classes("w-full")
        trans_mode = ui.input("Default trans mode", value="server_cycle").classes("w-full")
        cycle_ms = ui.input("Default cycle (ms)", value="200").classes("w-full")
        str_len = ui.input("Default string len", value="80").classes("w-full")
        subs = ui.textarea(
            "Subscriptions (JSON list: [{\"name\":\"Main.CURRENTIP\",\"alias\":\"CurrentIp\",\"plc_type\":\"STRING\",\"string_len\":64}])",
            value="[]",
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=d.close).props("flat")
            ui.button(
                "Add",
                on_click=lambda: _add_endpoint(
                    d,
                    client_id.value,
                    plc_ip.value,
                    ams.value,
                    ads_port.value,
                    trans_mode.value,
                    cycle_ms.value,
                    str_len.value,
                    subs.value,
                ),
            ).props("color=primary")
    d.open()


def _add_endpoint(dlg: ui.dialog, client_id: str, plc_ip: str, plc_ams_net_id: str, ads_port: str, default_trans_mode: str,
                  default_cycle_ms: str, default_string_len: str, subscriptions_raw: str) -> None:
    if not client_id.strip() or not plc_ip.strip() or not plc_ams_net_id.strip():
        ui.notify("Client ID, PLC IP and AMS Net ID are required.", type="negative")
        return
    ads_port_v = _parse_int(ads_port, "ADS Port must be an integer.")
    cycle_ms_v = _parse_int(default_cycle_ms, "Default cycle must be an integer.")
    str_len_v = _parse_int(default_string_len, "Default string len must be an integer.")
    subs_v = _parse_subscriptions(subscriptions_raw)
    if ads_port_v is None or cycle_ms_v is None or str_len_v is None or subs_v is None:
        return

    cfg = get_app_config()
    tw_cfg = cfg.workers.configs.setdefault("twincat", {})
    endpoints = list(tw_cfg.get("plc_endpoints", []))
    if any(e.get("client_id") == client_id for e in endpoints):
        ui.notify("TwinCAT client_id already exists.", type="negative")
        return

    endpoints.append({
        "client_id": client_id.strip(),
        "plc_ip": plc_ip.strip(),
        "plc_ams_net_id": plc_ams_net_id.strip(),
        "ads_port": ads_port_v,
        "default_trans_mode": default_trans_mode or "server_cycle",
        "default_cycle_ms": cycle_ms_v,
        "default_string_len": str_len_v,
        "subscriptions": subs_v,
    })
    tw_cfg["plc_endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("TwinCAT PLC added.", type="positive")
    dlg.close()
    wid = generate_wrapper_id(TWINCAT_LIST.id_prefix, client_id.strip())
    _render_endpoints.refresh(scroll_to=wid, highlight=wid)


def _update_endpoint(index: int, client_id: str, plc_ip: str, plc_ams_net_id: str, ads_port: str, default_trans_mode: str,
                     default_cycle_ms: str, default_string_len: str, subscriptions_raw: str) -> None:
    if not client_id.strip() or not plc_ip.strip() or not plc_ams_net_id.strip():
        ui.notify("Client ID, PLC IP and AMS Net ID are required.", type="negative")
        return
    ads_port_v = _parse_int(ads_port, "ADS Port must be an integer.")
    cycle_ms_v = _parse_int(default_cycle_ms, "Default cycle must be an integer.")
    str_len_v = _parse_int(default_string_len, "Default string len must be an integer.")
    subs_v = _parse_subscriptions(subscriptions_raw)
    if ads_port_v is None or cycle_ms_v is None or str_len_v is None or subs_v is None:
        return

    cfg = get_app_config()
    tw_cfg = cfg.workers.configs.setdefault("twincat", {})
    endpoints = list(tw_cfg.get("plc_endpoints", []))
    if index < 0 or index >= len(endpoints):
        ui.notify("TwinCAT endpoint not found.", type="negative")
        return

    endpoints[index] = {
        "client_id": client_id,
        "plc_ip": plc_ip.strip(),
        "plc_ams_net_id": plc_ams_net_id.strip(),
        "ads_port": ads_port_v,
        "default_trans_mode": default_trans_mode or "server_cycle",
        "default_cycle_ms": cycle_ms_v,
        "default_string_len": str_len_v,
        "subscriptions": subs_v,
    }
    tw_cfg["plc_endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("TwinCAT PLC updated.", type="positive")
    _render_endpoints.refresh()


def _delete_endpoint(index: int) -> None:
    cfg = get_app_config()
    tw_cfg = cfg.workers.configs.setdefault("twincat", {})
    endpoints = list(tw_cfg.get("plc_endpoints", []))
    if index < 0 or index >= len(endpoints):
        ui.notify("TwinCAT endpoint not found.", type="negative")
        return
    endpoints.pop(index)
    tw_cfg["plc_endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("TwinCAT PLC deleted.", type="positive")
    _render_endpoints.refresh()
