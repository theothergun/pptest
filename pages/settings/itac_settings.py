from __future__ import annotations

from typing import Callable

from nicegui import ui

from layout.context import PageContext
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import get_app_config, save_app_config

ITAC_LIST = ExpandableList(
    scroller_id="itac-scroll",
    id_prefix="itac-card",
    expanded_storage_key="itac_expanded_name",
    get_key=lambda ep: ep.get("name", ""),
)


def _parse_float(value: str, message: str) -> float | None:
    try:
        return float(str(value).strip())
    except Exception:
        ui.notify(message, type="negative")
        return None


def render(container: ui.element, _ctx: PageContext) -> None:
    with container.classes("w-full h-full min-h-0 overflow-hidden"):
        with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("iTAC").classes("text-2xl font-bold")
                ui.button("Add endpoint", on_click=_open_add_dialog).props("color=primary")
            ui.label("Configure iTAC worker connections.").classes("text-sm text-gray-500")

            with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-3 p-2") as scroller:
                scroller.props(f"id={ITAC_LIST.scroller_id}")
                _render_endpoints()


@ui.refreshable
def _render_endpoints(scroll_to: str | None = None, highlight: str | None = None) -> None:
    cfg = get_app_config()
    itac_cfg = cfg.workers.configs.setdefault("itac", {})
    endpoints = list(itac_cfg.get("endpoints", []))

    if not endpoints:
        ui.label("No iTAC endpoints configured yet.").classes("text-sm text-gray-500")
        return

    def refresh() -> None:
        _render_endpoints.refresh(scroll_to=None, highlight=None)

    def render_summary(ep: dict, _idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3 min-w-0"):
                ui.label(ep.get("name", "")).classes("font-medium")
                ui.label(ep.get("base_url", "")).classes("text-xs text-gray-500 truncate")
                ui.label(ep.get("station_number", "")).classes("text-xs text-gray-400")
            with ui.row().classes("items-center gap-2 shrink-0"):
                ui.button("Edit", on_click=toggle).props("flat color=primary")
                ui.button("Delete", on_click=delete).props("flat color=negative")

    def render_editor(ep: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-2"):
            ui.input("Name", value=ep.get("name", "")).props("readonly borderless").classes("flex-1")
            ui.button("Close", on_click=toggle).props("flat")

        with ui.row().classes("w-full gap-3"):
            base_url = ui.input("Base URL", value=ep.get("base_url", "")).classes("flex-1")
            station_number = ui.input("Station number", value=ep.get("station_number", "")).classes("flex-1")
            client = ui.input("Client", value=ep.get("client", "01")).classes("w-40")

        with ui.row().classes("w-full gap-3"):
            registration_type = ui.input("Registration type", value=ep.get("registration_type", "S")).classes("w-52")
            system_identifier = ui.input("System identifier", value=ep.get("system_identifier", "nicegui")).classes("flex-1")
            force_locale = ui.input("Force locale", value=ep.get("force_locale", "")).classes("w-52")
            timeout_s = ui.input("Timeout (s)", value=str(ep.get("timeout_s", 10.0))).classes("w-40")

        with ui.row().classes("w-full gap-3"):
            station_password = ui.input("Station password", value=ep.get("station_password", "")).props("type=password").classes("flex-1")
            user = ui.input("User", value=ep.get("user", "")).classes("flex-1")
            password = ui.input("Password", value=ep.get("password", "")).props("type=password").classes("flex-1")

        with ui.row().classes("w-full items-center gap-6"):
            verify_ssl = ui.switch("Verify SSL", value=ep.get("verify_ssl", True))
            auto_login = ui.switch("Auto login", value=ep.get("auto_login", True))
            visible_on_device_panel = ui.switch(
                "Visible on device panel",
                value=bool(ep.get("visible_on_device_panel", False)),
            )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                "Save",
                on_click=lambda i=idx, n=ep.get("name", ""), b=base_url, sn=station_number, c=client, rt=registration_type, si=system_identifier, sp=station_password, u=user, p=password, t=timeout_s, v=verify_ssl, a=auto_login, fl=force_locale:
                _update_endpoint(i, n, b.value, sn.value, c.value, rt.value, si.value, sp.value, u.value, p.value, t.value, bool(v.value), bool(a.value), fl.value, bool(visible_on_device_panel.value)),
            ).props("color=primary")
            ui.button("Delete", on_click=delete).props("flat color=negative")

    ITAC_LIST.render(
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
        ui.label("Add iTAC endpoint").classes("text-lg font-semibold")
        name = ui.input("Name").classes("w-full")
        base_url = ui.input("Base URL").classes("w-full")
        station_number = ui.input("Station number").classes("w-full")
        client = ui.input("Client", value="01").classes("w-full")
        registration_type = ui.input("Registration type", value="S").classes("w-full")
        system_identifier = ui.input("System identifier", value="nicegui").classes("w-full")
        station_password = ui.input("Station password").props("type=password").classes("w-full")
        user = ui.input("User").classes("w-full")
        password = ui.input("Password").props("type=password").classes("w-full")
        timeout_s = ui.input("Timeout (s)", value="10.0").classes("w-full")
        force_locale = ui.input("Force locale").classes("w-full")
        verify_ssl = ui.switch("Verify SSL", value=True)
        auto_login = ui.switch("Auto login", value=True)
        visible_on_device_panel = ui.switch("Visible on device panel", value=False)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=d.close).props("flat")
            ui.button(
                "Add",
                on_click=lambda: _add_endpoint(
                    d, name.value, base_url.value, station_number.value, client.value, registration_type.value,
                    system_identifier.value, station_password.value, user.value, password.value, timeout_s.value,
                    bool(verify_ssl.value), bool(auto_login.value), force_locale.value, bool(visible_on_device_panel.value)
                ),
            ).props("color=primary")
    d.open()


def _add_endpoint(dlg: ui.dialog, name: str, base_url: str, station_number: str, client: str, registration_type: str,
                  system_identifier: str, station_password: str, user: str, password: str, timeout_s: str,
                  verify_ssl: bool, auto_login: bool, force_locale: str, visible_on_device_panel: bool) -> None:
    if not name.strip() or not base_url.strip() or not station_number.strip():
        ui.notify("Name, base URL and station number are required.", type="negative")
        return
    timeout_v = _parse_float(timeout_s, "Timeout must be a number.")
    if timeout_v is None:
        return

    cfg = get_app_config()
    itac_cfg = cfg.workers.configs.setdefault("itac", {})
    endpoints = list(itac_cfg.get("endpoints", []))
    if any(e.get("name") == name for e in endpoints):
        ui.notify("iTAC endpoint name already exists.", type="negative")
        return

    endpoints.append({
        "name": name.strip(),
        "base_url": base_url.strip(),
        "station_number": station_number.strip(),
        "client": (client or "01").strip(),
        "registration_type": (registration_type or "S").strip(),
        "system_identifier": (system_identifier or "nicegui").strip(),
        "station_password": station_password or "",
        "user": user or "",
        "password": password or "",
        "timeout_s": timeout_v,
        "verify_ssl": bool(verify_ssl),
        "auto_login": bool(auto_login),
        "force_locale": force_locale or "",
        "visible_on_device_panel": bool(visible_on_device_panel),
    })
    itac_cfg["endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("iTAC endpoint added.", type="positive")
    dlg.close()
    wid = generate_wrapper_id(ITAC_LIST.id_prefix, name.strip())
    _render_endpoints.refresh(scroll_to=wid, highlight=wid)


def _update_endpoint(index: int, name: str, base_url: str, station_number: str, client: str, registration_type: str,
                     system_identifier: str, station_password: str, user: str, password: str, timeout_s: str,
                     verify_ssl: bool, auto_login: bool, force_locale: str, visible_on_device_panel: bool) -> None:
    if not name.strip() or not base_url.strip() or not station_number.strip():
        ui.notify("Name, base URL and station number are required.", type="negative")
        return
    timeout_v = _parse_float(timeout_s, "Timeout must be a number.")
    if timeout_v is None:
        return

    cfg = get_app_config()
    itac_cfg = cfg.workers.configs.setdefault("itac", {})
    endpoints = list(itac_cfg.get("endpoints", []))
    if index < 0 or index >= len(endpoints):
        ui.notify("iTAC endpoint not found.", type="negative")
        return

    endpoints[index] = {
        "name": name,
        "base_url": base_url.strip(),
        "station_number": station_number.strip(),
        "client": (client or "01").strip(),
        "registration_type": (registration_type or "S").strip(),
        "system_identifier": (system_identifier or "nicegui").strip(),
        "station_password": station_password or "",
        "user": user or "",
        "password": password or "",
        "timeout_s": timeout_v,
        "verify_ssl": bool(verify_ssl),
        "auto_login": bool(auto_login),
        "force_locale": force_locale or "",
        "visible_on_device_panel": bool(visible_on_device_panel),
    }
    itac_cfg["endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("iTAC endpoint updated.", type="positive")
    _render_endpoints.refresh()


def _delete_endpoint(index: int) -> None:
    cfg = get_app_config()
    itac_cfg = cfg.workers.configs.setdefault("itac", {})
    endpoints = list(itac_cfg.get("endpoints", []))
    if index < 0 or index >= len(endpoints):
        ui.notify("iTAC endpoint not found.", type="negative")
        return
    endpoints.pop(index)
    itac_cfg["endpoints"] = endpoints
    save_app_config(cfg)
    ui.notify("iTAC endpoint deleted.", type="positive")
    _render_endpoints.refresh()
