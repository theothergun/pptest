from __future__ import annotations

import re
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


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)


def _infer_alias_from_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    return raw.split(".")[-1].replace("[", "_").replace("]", "").strip("_")


def _infer_plc_type(symbol_type: str, default_len: int) -> tuple[str, int]:
    t = str(symbol_type or "").strip().upper()
    if not t:
        return "UINT", default_len

    m = re.match(r"^(W?STRING)(?:\s*[\(\[]\s*(\d+)\s*[\)\]])?$", t)
    if m:
        n = int(m.group(2) or default_len or 80)
        return f"{m.group(1)}({n})", n

    known = {
        "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
        "SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT",
        "REAL", "LREAL", "TIME", "DATE", "DT", "TOD",
    }
    if t in known:
        return t, default_len
    return t, default_len


def _normalize_subscriptions(items: list[dict[str, Any]], default_string_len: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        alias = str(item.get("alias") or "").strip()
        plc_type_raw = str(item.get("plc_type") or "UINT").strip()
        string_len = _coerce_int(item.get("string_len", default_string_len), default_string_len)
        plc_type, inferred_len = _infer_plc_type(plc_type_raw, string_len)
        if plc_type.startswith(("STRING", "WSTRING")):
            string_len = inferred_len
        if name in seen:
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "alias": alias,
                "plc_type": plc_type,
                "string_len": max(1, int(string_len)),
            }
        )
    return out


def _load_pyads():
    try:
        import pyads as _pyads  # type: ignore
        return _pyads
    except Exception:
        pass

    try:
        from services.workers.twincat_worker import _import_pyads_with_dll_dirs
        return _import_pyads_with_dll_dirs()
    except Exception:
        return None


def _read_plc_symbols(ams_net_id: str, plc_ip: str, ads_port: int, timeout_ms: int = 2000) -> list[dict[str, Any]]:
    pyads = _load_pyads()
    if pyads is None:
        raise RuntimeError("pyads not available")

    conn = pyads.Connection(str(ams_net_id).strip(), int(ads_port), str(plc_ip).strip())
    conn.open()
    conn.set_timeout(int(timeout_ms))
    conn.read_device_info()
    try:
        symbols = conn.get_all_symbols()
    finally:
        conn.close()

    result: list[dict[str, Any]] = []
    for sym in symbols or []:
        name = str(getattr(sym, "name", "") or "").strip()
        if not name:
            continue
        symbol_type = str(getattr(sym, "symbol_type", "") or "").strip()
        plc_type, string_len = _infer_plc_type(symbol_type, 80)
        result.append(
            {
                "name": name,
                "symbol_type": symbol_type,
                "plc_type": plc_type,
                "string_len": string_len,
                "comment": str(getattr(sym, "comment", "") or ""),
            }
        )

    result.sort(key=lambda x: x["name"])
    return result


def _build_subscriptions_editor(
    initial_subscriptions: list[dict[str, Any]],
    default_len_getter: Callable[[], Any],
    plc_params_getter: Callable[[], tuple[str, str, int]],
) -> Callable[[], list[dict[str, Any]]]:
    state = {
        "rows": _normalize_subscriptions(
            list(initial_subscriptions or []),
            max(1, _coerce_int(default_len_getter(), 80)),
        )
    }

    def _current_default_len() -> int:
        return max(1, _coerce_int(default_len_getter(), 80))

    @ui.refreshable
    def _render_rows() -> None:
        if not state["rows"]:
            ui.label("No variables configured yet.").classes("text-sm text-gray-500")
            return

        for idx, row in enumerate(state["rows"]):
            with ui.card().classes("w-full p-3 gap-2"):
                with ui.row().classes("w-full items-center gap-2"):
                    ui.input(
                        "Variable name",
                        value=row.get("name", ""),
                        on_change=lambda e, r=row: r.__setitem__("name", str(e.value or "").strip()),
                    ).classes("flex-[2]")
                    ui.input(
                        "Alias",
                        value=row.get("alias", ""),
                        on_change=lambda e, r=row: r.__setitem__("alias", str(e.value or "").strip()),
                    ).classes("flex-1")
                    ui.input(
                        "PLC type",
                        value=row.get("plc_type", "UINT"),
                        on_change=lambda e, r=row: r.__setitem__("plc_type", str(e.value or "UINT").strip()),
                    ).classes("w-40")
                    ui.input(
                        "String len",
                        value=str(row.get("string_len", 80)),
                        on_change=lambda e, r=row: r.__setitem__("string_len", _coerce_int(e.value, _current_default_len())),
                    ).classes("w-32")
                    ui.button("Remove", on_click=lambda i=idx: _remove_row(i)).props("flat color=negative")

    def _remove_row(index: int) -> None:
        if 0 <= index < len(state["rows"]):
            state["rows"].pop(index)
            _render_rows.refresh()

    def _add_row(item: dict[str, Any] | None = None) -> None:
        current_default = _current_default_len()
        seed = {
            "name": "",
            "alias": "",
            "plc_type": "UINT",
            "string_len": current_default,
        }
        if isinstance(item, dict):
            seed.update(item)
        state["rows"].append(seed)
        _render_rows.refresh()

    def _open_symbol_picker() -> None:
        ams_net_id, plc_ip, ads_port = plc_params_getter()
        if not str(ams_net_id or "").strip() or not str(plc_ip or "").strip():
            ui.notify("Set PLC IP and AMS Net ID first.", type="negative")
            return

        dialog = ui.dialog()
        symbols_state: dict[str, Any] = {"all": [], "selected": set(), "page": 0, "page_size": 300}

        with dialog, ui.card().classes("w-[1100px] max-w-[95vw]"):
            ui.label("Import PLC Symbols").classes("text-lg font-semibold")
            ui.label(f"{plc_ip}:{ads_port}  |  AMS {ams_net_id}").classes("text-sm text-gray-500")

            filter_input = ui.input(
                "Filter",
                placeholder="e.g. MAIN.module.zenonVisu",
                on_change=lambda _e: _render_symbols.refresh(),
            ).classes("w-full")
            quick_add_input = ui.input("Add by full variable name", placeholder="MAIN.module.zenonVisu.Stop").classes("w-full")

            @ui.refreshable
            def _render_symbols() -> None:
                items = list(symbols_state["all"])
                needle = str(filter_input.value or "").strip().lower()
                if needle:
                    items = [s for s in items if needle in str(s.get("name", "")).lower()]

                if not items:
                    ui.label("No symbols loaded (or no match).").classes("text-sm text-gray-500")
                    return

                page_size = max(50, int(symbols_state.get("page_size", 300) or 300))
                page = max(0, int(symbols_state.get("page", 0) or 0))
                pages = max(1, (len(items) + page_size - 1) // page_size)
                if page >= pages:
                    page = pages - 1
                    symbols_state["page"] = page
                start = page * page_size
                end = min(len(items), start + page_size)
                page_items = items[start:end]

                ui.label(f"Showing {start + 1}-{end} of {len(items)} symbols").classes("text-xs text-gray-500")
                with ui.row().classes("w-full items-center justify-end gap-2"):
                    ui.button("Prev", on_click=lambda: _set_page(page - 1)).props("flat")
                    ui.label(f"Page {page + 1}/{pages}").classes("text-xs text-gray-500")
                    ui.button("Next", on_click=lambda: _set_page(page + 1)).props("flat")

                with ui.column().classes("w-full h-96 overflow-y-auto gap-1"):
                    for sym in page_items:
                        name = str(sym.get("name", ""))
                        checked = name in symbols_state["selected"]
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.checkbox(
                                value=checked,
                                on_change=lambda e, n=name: _set_selected(n, bool(e.value)),
                            )
                            ui.label(name).classes("flex-1 text-sm")
                            ui.label(str(sym.get("symbol_type", ""))).classes("w-44 text-xs text-gray-500")

            def _set_page(new_page: int) -> None:
                symbols_state["page"] = max(0, int(new_page))
                _render_symbols.refresh()

            def _set_selected(name: str, checked: bool) -> None:
                if checked:
                    symbols_state["selected"].add(name)
                else:
                    symbols_state["selected"].discard(name)

            def _load_symbols() -> None:
                try:
                    rows = _read_plc_symbols(ams_net_id, plc_ip, int(ads_port), timeout_ms=2000)
                except Exception as ex:
                    ui.notify(f"Failed to read symbols: {ex}", type="negative")
                    return
                symbols_state["all"] = rows
                symbols_state["selected"] = set()
                symbols_state["page"] = 0
                _render_symbols.refresh()
                ui.notify(f"Loaded {len(rows)} symbols.", type="positive")

            def _quick_add() -> None:
                full_name = str(quick_add_input.value or "").strip()
                if not full_name:
                    ui.notify("Enter a full variable name.", type="negative")
                    return
                existing_names = {str(r.get("name", "")).strip() for r in state["rows"]}
                if full_name in existing_names:
                    ui.notify("Variable already in list.", type="warning")
                    return
                state["rows"].append(
                    {
                        "name": full_name,
                        "alias": _infer_alias_from_name(full_name),
                        "plc_type": "UINT",
                        "string_len": _current_default_len(),
                    }
                )
                _render_rows.refresh()
                ui.notify("Variable added. Adjust PLC type if needed.", type="positive")
                dialog.close()

            def _add_selected() -> None:
                selected_names = set(symbols_state["selected"])
                if not selected_names:
                    ui.notify("No symbols selected.", type="negative")
                    return

                existing_names = {str(r.get("name", "")).strip() for r in state["rows"]}
                added = 0
                for sym in symbols_state["all"]:
                    name = str(sym.get("name", "")).strip()
                    if not name or name not in selected_names or name in existing_names:
                        continue
                    existing_names.add(name)
                    state["rows"].append(
                        {
                            "name": name,
                            "alias": _infer_alias_from_name(name),
                            "plc_type": str(sym.get("plc_type", "UINT") or "UINT"),
                            "string_len": _coerce_int(sym.get("string_len", _current_default_len()), _current_default_len()),
                        }
                    )
                    added += 1

                _render_rows.refresh()
                ui.notify(f"Added {added} variable(s).", type="positive")
                dialog.close()

            with ui.row().classes("w-full justify-between"):
                with ui.row().classes("gap-2"):
                    ui.button("Load symbols", on_click=_load_symbols).props("color=primary")
                    ui.button("Refresh view", on_click=lambda: _render_symbols.refresh()).props("flat")
                with ui.row().classes("gap-2"):
                    ui.button("Add typed name", on_click=_quick_add).props("flat")
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Add selected", on_click=_add_selected).props("color=primary")

            _render_symbols()

        dialog.open()

    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Variables").classes("text-sm font-medium")
            with ui.row().classes("gap-2"):
                ui.button("Add variable", on_click=lambda: _add_row()).props("flat color=primary")
                ui.button("Import from PLC symbols", on_click=_open_symbol_picker).props("flat color=primary")
        _render_rows()

    def _collect() -> list[dict[str, Any]]:
        return _normalize_subscriptions(state["rows"], _current_default_len())

    return _collect


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
        visible_on_device_panel = ui.switch(
            "Visible on device panel",
            value=bool(ep.get("visible_on_device_panel", False)),
        )

        subs_getter = _build_subscriptions_editor(
            initial_subscriptions=list(ep.get("subscriptions", [])),
            default_len_getter=lambda sl=str_len: sl.value,
            plc_params_getter=lambda a=ams, i=plc_ip, p=ads_port: (
                str(a.value or "").strip(),
                str(i.value or "").strip(),
                _coerce_int(p.value, 851),
            ),
        )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                "Save",
                on_click=lambda i=idx, cid=ep.get("client_id", ""), ip=plc_ip, net=ams, ap=ads_port, tm=trans_mode, cm=cycle_ms, sl=str_len:
                _update_endpoint(
                    i,
                    cid,
                    ip.value,
                    net.value,
                    ap.value,
                    tm.value,
                    cm.value,
                    sl.value,
                    subs_getter(),
                    bool(visible_on_device_panel.value),
                ),
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
        visible_on_device_panel = ui.switch("Visible on device panel", value=False)
        subs_getter = _build_subscriptions_editor(
            initial_subscriptions=[],
            default_len_getter=lambda sl=str_len: sl.value,
            plc_params_getter=lambda a=ams, i=plc_ip, p=ads_port: (
                str(a.value or "").strip(),
                str(i.value or "").strip(),
                _coerce_int(p.value, 851),
            ),
        )

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
                    subs_getter(),
                    bool(visible_on_device_panel.value),
                ),
            ).props("color=primary")
    d.open()


def _add_endpoint(dlg: ui.dialog, client_id: str, plc_ip: str, plc_ams_net_id: str, ads_port: str, default_trans_mode: str,
                  default_cycle_ms: str, default_string_len: str, subscriptions: list[dict[str, Any]], visible_on_device_panel: bool) -> None:
    if not client_id.strip() or not plc_ip.strip() or not plc_ams_net_id.strip():
        ui.notify("Client ID, PLC IP and AMS Net ID are required.", type="negative")
        return
    ads_port_v = _parse_int(ads_port, "ADS Port must be an integer.")
    cycle_ms_v = _parse_int(default_cycle_ms, "Default cycle must be an integer.")
    str_len_v = _parse_int(default_string_len, "Default string len must be an integer.")
    if ads_port_v is None or cycle_ms_v is None or str_len_v is None:
        return
    subs_v = _normalize_subscriptions(subscriptions, max(1, int(str_len_v)))

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
        "visible_on_device_panel": bool(visible_on_device_panel),
    })
    tw_cfg["plc_endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("TwinCAT PLC added.", type="positive")
    dlg.close()
    wid = generate_wrapper_id(TWINCAT_LIST.id_prefix, client_id.strip())
    _render_endpoints.refresh(scroll_to=wid, highlight=wid)


def _update_endpoint(index: int, client_id: str, plc_ip: str, plc_ams_net_id: str, ads_port: str, default_trans_mode: str,
                     default_cycle_ms: str, default_string_len: str, subscriptions: list[dict[str, Any]], visible_on_device_panel: bool) -> None:
    if not client_id.strip() or not plc_ip.strip() or not plc_ams_net_id.strip():
        ui.notify("Client ID, PLC IP and AMS Net ID are required.", type="negative")
        return
    ads_port_v = _parse_int(ads_port, "ADS Port must be an integer.")
    cycle_ms_v = _parse_int(default_cycle_ms, "Default cycle must be an integer.")
    str_len_v = _parse_int(default_string_len, "Default string len must be an integer.")
    if ads_port_v is None or cycle_ms_v is None or str_len_v is None:
        return
    subs_v = _normalize_subscriptions(subscriptions, max(1, int(str_len_v)))

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
        "visible_on_device_panel": bool(visible_on_device_panel),
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
