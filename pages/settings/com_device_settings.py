from __future__ import annotations

from typing import Callable

from nicegui import ui

from layout.context import PageContext
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import get_app_config, save_app_config

COM_DEVICE_LIST = ExpandableList(
    scroller_id="com-device-scroll",
    id_prefix="com-device-card",
    expanded_storage_key="com_device_expanded_device_id",
    get_key=lambda ep: ep.get("device_id", ""),
)


def _parse_int(value: str, message: str) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        ui.notify(message, type="negative")
        return None


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
                ui.label("COM Device").classes("text-2xl font-bold")
                ui.button("Add device", on_click=_open_add_dialog).props("color=primary")
            ui.label("Configure COM device worker devices.").classes("text-sm text-gray-500")

            with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-3 p-2") as scroller:
                scroller.props(f"id={COM_DEVICE_LIST.scroller_id}")
                _render_devices()


@ui.refreshable
def _render_devices(scroll_to: str | None = None, highlight: str | None = None) -> None:
    cfg = get_app_config()
    com_cfg = cfg.workers.configs.setdefault("com_device", {})
    devices = list(com_cfg.get("devices", []))

    if not devices:
        ui.label("No COM devices configured yet.").classes("text-sm text-gray-500")
        return

    def refresh() -> None:
        _render_devices.refresh(scroll_to=None, highlight=None)

    def render_summary(dev: dict, _idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3 min-w-0"):
                ui.label(dev.get("device_id", "")).classes("font-medium")
                ui.label(dev.get("port", "")).classes("text-xs text-gray-500")
                ui.label(dev.get("mode", "line")).classes("text-xs text-gray-400")
            with ui.row().classes("items-center gap-2 shrink-0"):
                ui.button("Edit", on_click=toggle).props("flat color=primary")
                ui.button("Delete", on_click=delete).props("flat color=negative")

    def render_editor(dev: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
        with ui.row().classes("w-full items-center justify-between gap-2"):
            ui.input("Device ID", value=dev.get("device_id", "")).props("readonly borderless").classes("flex-1")
            ui.button("Close", on_click=toggle).props("flat")

        with ui.row().classes("w-full gap-3"):
            port = ui.input("Port", value=dev.get("port", "")).classes("w-52")
            baudrate = ui.input("Baudrate", value=str(dev.get("baudrate", 115200))).classes("w-52")
            bytesize = ui.input("Bytesize", value=str(dev.get("bytesize", 8))).classes("w-40")
            parity = ui.input("Parity", value=dev.get("parity", "N")).classes("w-40")
            stopbits = ui.input("Stopbits", value=str(dev.get("stopbits", 1.0))).classes("w-40")
            mode = ui.input("Mode", value=dev.get("mode", "line")).classes("w-40")

        with ui.row().classes("w-full gap-3"):
            timeout_s = ui.input("Timeout (s)", value=str(dev.get("timeout_s", 0.2))).classes("w-52")
            write_timeout_s = ui.input("Write timeout (s)", value=str(dev.get("write_timeout_s", 0.5))).classes("w-52")
            delimiter = ui.input("Delimiter", value=dev.get("delimiter", "\\n")).classes("w-52")
            encoding = ui.input("Encoding", value=dev.get("encoding", "utf-8")).classes("w-52")

        with ui.row().classes("w-full gap-3"):
            read_chunk_size = ui.input("Read chunk size", value=str(dev.get("read_chunk_size", 256))).classes("w-52")
            max_line_len = ui.input("Max line len", value=str(dev.get("max_line_len", 4096))).classes("w-52")
            reconnect_min_s = ui.input("Reconnect min (s)", value=str(dev.get("reconnect_min_s", 0.5))).classes("w-52")
            reconnect_max_s = ui.input("Reconnect max (s)", value=str(dev.get("reconnect_max_s", 5.0))).classes("w-52")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                "Save",
                on_click=lambda i=idx, did=dev.get("device_id", ""), p=port, b=baudrate, by=bytesize, pa=parity, st=stopbits, mo=mode, to=timeout_s, wto=write_timeout_s, de=delimiter, en=encoding, rc=read_chunk_size, ml=max_line_len, rmi=reconnect_min_s, rma=reconnect_max_s:
                _update_device(i, did, p.value, b.value, by.value, pa.value, st.value, mo.value, to.value, wto.value, de.value, en.value, rc.value, ml.value, rmi.value, rma.value),
            ).props("color=primary")
            ui.button("Delete", on_click=delete).props("flat color=negative")

    COM_DEVICE_LIST.render(
        devices,
        render_summary=render_summary,
        render_editor=render_editor,
        on_delete=_delete_device,
        refresh=refresh,
        scroll_to=scroll_to,
        highlight=highlight,
    )


def _open_add_dialog() -> None:
    d = ui.dialog()
    with d, ui.card().classes("w-[900px] max-w-[95vw]"):
        ui.label("Add COM device").classes("text-lg font-semibold")
        device_id = ui.input("Device ID").classes("w-full")
        port = ui.input("Port", value="COM1").classes("w-full")
        baudrate = ui.input("Baudrate", value="115200").classes("w-full")
        bytesize = ui.input("Bytesize", value="8").classes("w-full")
        parity = ui.input("Parity", value="N").classes("w-full")
        stopbits = ui.input("Stopbits", value="1.0").classes("w-full")
        timeout_s = ui.input("Timeout (s)", value="0.2").classes("w-full")
        write_timeout_s = ui.input("Write timeout (s)", value="0.5").classes("w-full")
        mode = ui.input("Mode", value="line").classes("w-full")
        delimiter = ui.input("Delimiter", value="\\n").classes("w-full")
        encoding = ui.input("Encoding", value="utf-8").classes("w-full")
        read_chunk_size = ui.input("Read chunk size", value="256").classes("w-full")
        max_line_len = ui.input("Max line len", value="4096").classes("w-full")
        reconnect_min_s = ui.input("Reconnect min (s)", value="0.5").classes("w-full")
        reconnect_max_s = ui.input("Reconnect max (s)", value="5.0").classes("w-full")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=d.close).props("flat")
            ui.button(
                "Add",
                on_click=lambda: _add_device(
                    d, device_id.value, port.value, baudrate.value, bytesize.value, parity.value, stopbits.value,
                    mode.value, timeout_s.value, write_timeout_s.value, delimiter.value, encoding.value,
                    read_chunk_size.value, max_line_len.value, reconnect_min_s.value, reconnect_max_s.value
                ),
            ).props("color=primary")
    d.open()


def _add_device(dlg: ui.dialog, device_id: str, port: str, baudrate: str, bytesize: str, parity: str, stopbits: str, mode: str,
                timeout_s: str, write_timeout_s: str, delimiter: str, encoding: str, read_chunk_size: str, max_line_len: str,
                reconnect_min_s: str, reconnect_max_s: str) -> None:
    if not device_id.strip() or not port.strip():
        ui.notify("Device ID and port are required.", type="negative")
        return
    parsed = _parse_device_numbers(baudrate, bytesize, stopbits, timeout_s, write_timeout_s, read_chunk_size, max_line_len, reconnect_min_s, reconnect_max_s)
    if parsed is None:
        return
    baud_v, bytes_v, stop_v, timeout_v, write_timeout_v, read_chunk_v, max_line_v, rec_min_v, rec_max_v = parsed

    cfg = get_app_config()
    com_cfg = cfg.workers.configs.setdefault("com_device", {})
    devices = list(com_cfg.get("devices", []))
    if any(d.get("device_id") == device_id for d in devices):
        ui.notify("COM device_id already exists.", type="negative")
        return

    devices.append({
        "device_id": device_id.strip(),
        "port": port.strip(),
        "baudrate": baud_v,
        "bytesize": bytes_v,
        "parity": (parity or "N").strip(),
        "stopbits": stop_v,
        "timeout_s": timeout_v,
        "write_timeout_s": write_timeout_v,
        "mode": (mode or "line").strip(),
        "delimiter": delimiter if delimiter != "" else "\\n",
        "encoding": encoding or "utf-8",
        "read_chunk_size": read_chunk_v,
        "max_line_len": max_line_v,
        "reconnect_min_s": rec_min_v,
        "reconnect_max_s": rec_max_v,
    })
    com_cfg["devices"] = devices
    save_app_config(cfg)
    ui.notify("COM device added.", type="positive")
    dlg.close()
    wid = generate_wrapper_id(COM_DEVICE_LIST.id_prefix, device_id.strip())
    _render_devices.refresh(scroll_to=wid, highlight=wid)


def _update_device(index: int, device_id: str, port: str, baudrate: str, bytesize: str, parity: str, stopbits: str, mode: str,
                   timeout_s: str, write_timeout_s: str, delimiter: str, encoding: str, read_chunk_size: str, max_line_len: str,
                   reconnect_min_s: str, reconnect_max_s: str) -> None:
    if not device_id.strip() or not port.strip():
        ui.notify("Device ID and port are required.", type="negative")
        return
    parsed = _parse_device_numbers(baudrate, bytesize, stopbits, timeout_s, write_timeout_s, read_chunk_size, max_line_len, reconnect_min_s, reconnect_max_s)
    if parsed is None:
        return
    baud_v, bytes_v, stop_v, timeout_v, write_timeout_v, read_chunk_v, max_line_v, rec_min_v, rec_max_v = parsed

    cfg = get_app_config()
    com_cfg = cfg.workers.configs.setdefault("com_device", {})
    devices = list(com_cfg.get("devices", []))
    if index < 0 or index >= len(devices):
        ui.notify("COM device not found.", type="negative")
        return

    devices[index] = {
        "device_id": device_id,
        "port": port.strip(),
        "baudrate": baud_v,
        "bytesize": bytes_v,
        "parity": (parity or "N").strip(),
        "stopbits": stop_v,
        "timeout_s": timeout_v,
        "write_timeout_s": write_timeout_v,
        "mode": (mode or "line").strip(),
        "delimiter": delimiter if delimiter != "" else "\\n",
        "encoding": encoding or "utf-8",
        "read_chunk_size": read_chunk_v,
        "max_line_len": max_line_v,
        "reconnect_min_s": rec_min_v,
        "reconnect_max_s": rec_max_v,
    }
    com_cfg["devices"] = devices
    save_app_config(cfg)
    ui.notify("COM device updated.", type="positive")
    _render_devices.refresh()


def _delete_device(index: int) -> None:
    cfg = get_app_config()
    com_cfg = cfg.workers.configs.setdefault("com_device", {})
    devices = list(com_cfg.get("devices", []))
    if index < 0 or index >= len(devices):
        ui.notify("COM device not found.", type="negative")
        return
    devices.pop(index)
    com_cfg["devices"] = devices
    save_app_config(cfg)
    ui.notify("COM device deleted.", type="positive")
    _render_devices.refresh()


def _parse_device_numbers(baudrate: str, bytesize: str, stopbits: str, timeout_s: str, write_timeout_s: str,
                          read_chunk_size: str, max_line_len: str, reconnect_min_s: str, reconnect_max_s: str) -> tuple[int, int, float, float, float, int, int, float, float] | None:
    baud_v = _parse_int(baudrate, "Baudrate must be an integer.")
    bytes_v = _parse_int(bytesize, "Bytesize must be an integer.")
    stop_v = _parse_float(stopbits, "Stopbits must be a number.")
    timeout_v = _parse_float(timeout_s, "Timeout must be a number.")
    write_timeout_v = _parse_float(write_timeout_s, "Write timeout must be a number.")
    read_chunk_v = _parse_int(read_chunk_size, "Read chunk size must be an integer.")
    max_line_v = _parse_int(max_line_len, "Max line len must be an integer.")
    rec_min_v = _parse_float(reconnect_min_s, "Reconnect min must be a number.")
    rec_max_v = _parse_float(reconnect_max_s, "Reconnect max must be a number.")
    values = (baud_v, bytes_v, stop_v, timeout_v, write_timeout_v, read_chunk_v, max_line_v, rec_min_v, rec_max_v)
    if any(v is None for v in values):
        return None
    return values  # type: ignore[return-value]
