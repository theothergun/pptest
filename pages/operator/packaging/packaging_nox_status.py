from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.app_config import get_app_config, get_twincat_plc_endpoints
from services.worker_commands import TwinCatCommands
from services.worker_topics import WorkerTopics


KNOWN_WRITABLE_ALIASES: set[str] = {
    "Ack_mes",
    "Counter_ACK",
    "Dummy_enabled",
    "Result_code_mes",
    "Result_text_mes",
    "Working_Light",
    "Insight_Light",
    "Ring_Light",
}


def render(container: ui.element, ctx: PageContext) -> None:
    endpoint = _pick_endpoint()
    specs = _load_specs(endpoint)
    groups = _group_specs(specs)

    runtime_values: dict[str, Any] = {}
    rt = {
        "connected": False,
        "state": "Disconnected",
        "last_error": "",
        "last_write": "-",
    }
    row_refs: dict[str, dict[str, Any]] = {}

    sub = None
    if endpoint and ctx.worker_bus:
        sub = ctx.worker_bus.subscribe_many(
            [
                WorkerTopics.CLIENT_CONNECTED,
                WorkerTopics.CLIENT_DISCONNECTED,
                WorkerTopics.VALUE_CHANGED,
                WorkerTopics.ERROR,
                WorkerTopics.WRITE_ERROR,
                WorkerTopics.WRITE_FINISHED,
            ]
        )

    def _write_value(spec: dict[str, Any], editor: Any) -> None:
        if not endpoint or not ctx.workers:
            ui.notify("TwinCAT endpoint is not available", color="negative")
            return
        handle = ctx.workers.get("twincat")
        if handle is None:
            ui.notify("TwinCAT worker is not available", color="negative")
            return
        try:
            raw = getattr(editor, "value", None)
            value = _coerce_value(raw, str(spec.get("plc_type") or ""))
        except Exception as ex:
            ui.notify(f"Invalid value: {ex}", color="warning")
            return
        write_name = str(spec.get("alias") or spec.get("name") or "")
        handle.send(
            TwinCatCommands.WRITE,
            client_id=str(endpoint.get("client_id") or ""),
            name=write_name,
            value=value,
            plc_type=str(spec.get("plc_type") or ""),
            string_len=int(spec.get("string_len", 80) or 80),
        )
        rt["last_write"] = f"Requested: {write_name}"

    def _build_content(_parent: ui.element) -> None:
        ui.add_head_html(
            """
<style>
.pnx-shell {
  background: linear-gradient(135deg, var(--surface-muted) 0%, var(--app-background) 100%);
  border: 1px solid var(--input-border);
  border-radius: 18px;
}
.pnx-card {
  background: var(--surface);
  border: 1px solid var(--input-border);
  border-radius: 14px;
}
.pnx-var-row {
  border-bottom: 1px solid var(--surface-muted);
}
.pnx-key {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
"""
        )

        with ui.column().classes("pnx-shell w-full h-full min-h-0 gap-3 p-3"):
            with ui.card().classes("pnx-card w-full p-3"):
                ui.label("Packaging NOX TwinCAT Status").classes("text-xl font-bold")
                if endpoint:
                    ui.label(f"PLC: {endpoint.get('client_id', '-')} | {endpoint.get('plc_ip', '-')}").classes(
                        "text-xs text-gray-600"
                    )
                else:
                    ui.label("No TwinCAT endpoint configured in active config").classes("text-xs text-red-700")

                with ui.row().classes("w-full gap-2 mt-2 items-center"):
                    conn_badge = ui.badge("Disconnected").props("color=negative text-color=white")
                    err_badge = ui.badge("-").props("color=grey-7 text-color=white")
                    write_badge = ui.badge("-").props("color=primary text-color=white")

            with ui.row().classes("w-full gap-3 items-start"):
                for group_name, group_specs in groups:
                    with ui.card().classes("pnx-card min-w-[420px] max-w-full grow p-3"):
                        with ui.row().classes("w-full items-center"):
                            ui.label(group_name).classes("text-sm font-bold")
                            ui.space()
                            writable_count = len([s for s in group_specs if bool(s.get("writable", False))])
                            ui.badge(f"{len(group_specs)} tags").props("outline")
                            ui.badge(f"{writable_count} writable").props("color=info text-color=white")

                        for spec in group_specs:
                            sid = str(spec.get("id"))
                            with ui.row().classes("pnx-var-row w-full items-center gap-2 py-2"):
                                with ui.column().classes("w-[260px] gap-0"):
                                    ui.label(str(spec.get("alias") or spec.get("name") or "")).classes("text-sm font-semibold")
                                    ui.label(str(spec.get("name") or "")).classes("pnx-key break-all")
                                value_label = ui.label("-").classes("text-sm font-mono w-[220px] text-right")
                                value_label.style("white-space: nowrap; overflow: hidden; text-overflow: ellipsis;")

                                if bool(spec.get("writable", False)):
                                    editor_kind = _editor_kind(str(spec.get("plc_type") or ""))
                                    if editor_kind == "bool":
                                        editor = ui.switch(value=False).props("dense")
                                    elif editor_kind == "number":
                                        editor = ui.number(value=0).props("dense outlined")
                                    else:
                                        editor = ui.input(value="").props("dense outlined")
                                        editor.classes("w-[180px]")
                                    ui.button("Use", on_click=lambda _e=None, s=dict(spec), e=editor: _load_current_into_editor(s, e, runtime_values)).props("flat dense")
                                    ui.button("Write", on_click=lambda _e=None, s=dict(spec), e=editor: _write_value(s, e)).props("dense color=primary")
                                else:
                                    ui.badge("RO").props("outline color=grey")
                                row_refs[sid] = {"value_label": value_label, "spec": dict(spec)}

        def _refresh_ui() -> None:
            conn_badge.set_text("Connected" if bool(rt["connected"]) else "Disconnected")
            conn_badge.props(f"color={'positive' if bool(rt['connected']) else 'negative'} text-color=white")
            err_badge.set_text(str(rt.get("last_error") or "-")[:60])
            err_badge.props(f"color={'negative' if rt.get('last_error') else 'grey-7'} text-color=white")
            write_badge.set_text(str(rt.get("last_write") or "-")[:60])
            for ref in row_refs.values():
                spec = ref.get("spec", {})
                value_label = ref.get("value_label")
                if value_label is None:
                    continue
                value = _current_value(spec, runtime_values)
                try:
                    value_label.set_text(_to_text(value))
                except Exception:
                    pass

        ui.timer(0.3, _refresh_ui)

    def _drain_runtime() -> None:
        if sub is None or endpoint is None:
            return
        endpoint_id = str(endpoint.get("client_id") or "")
        while True:
            try:
                msg = sub.queue.get_nowait()
            except queue.Empty:
                break
            source = str(getattr(msg, "source", "") or "")
            source_id = str(getattr(msg, "source_id", "") or "")
            topic = str(getattr(msg, "topic", "") or "")
            payload = getattr(msg, "payload", None) or {}
            if source != "twincat" or source_id != endpoint_id:
                continue
            if topic == str(WorkerTopics.CLIENT_CONNECTED):
                rt["connected"] = True
                rt["state"] = "Connected"
                continue
            if topic == str(WorkerTopics.CLIENT_DISCONNECTED):
                rt["connected"] = False
                rt["state"] = "Disconnected"
                rt["last_error"] = str(payload.get("reason") or "Disconnected")
                continue
            if topic == str(WorkerTopics.ERROR):
                rt["last_error"] = str(payload.get("error") or "TwinCAT error")
                continue
            if topic == str(WorkerTopics.WRITE_ERROR):
                rt["last_error"] = str(payload.get("error") or "Write failed")
                rt["last_write"] = f"Write error: {payload.get('key') or '-'}"
                continue
            if topic == str(WorkerTopics.WRITE_FINISHED):
                rt["last_write"] = f"Write finished: {payload.get('key') or '-'}"
                continue
            if topic != str(WorkerTopics.VALUE_CHANGED):
                continue
            key = str(payload.get("key") or "")
            if not key:
                continue
            runtime_values[key] = payload.get("value")

    def _cleanup() -> None:
        try:
            if sub is not None:
                sub.close()
        except Exception:
            pass
        try:
            drain_timer.cancel()
        except Exception:
            pass

    drain_timer = ui.timer(0.15, _drain_runtime)
    ui.context.client.on_disconnect(_cleanup)

    build_page(
        ctx,
        container,
        title="Packaging NOX Status",
        content=_build_content,
        show_action_bar=False,
    )


def _pick_endpoint() -> dict[str, Any] | None:
    from_file = _endpoint_from_nox_packaging_file()
    if from_file is not None:
        return from_file

    cfg = get_app_config()
    endpoints = get_twincat_plc_endpoints(cfg)
    if not endpoints:
        return None
    for endpoint in endpoints:
        if str(getattr(endpoint, "client_id", "")) == "Beckhoff-PLC":
            return {
                "client_id": str(getattr(endpoint, "client_id", "")),
                "plc_ip": str(getattr(endpoint, "plc_ip", "")),
                "subscriptions": list(getattr(endpoint, "subscriptions", []) or []),
            }
    first = endpoints[0]
    return {
        "client_id": str(getattr(first, "client_id", "")),
        "plc_ip": str(getattr(first, "plc_ip", "")),
        "subscriptions": list(getattr(first, "subscriptions", []) or []),
    }


def _endpoint_from_nox_packaging_file() -> dict[str, Any] | None:
    cfg_path = Path("config/sets/NOX_Packaging.json")
    if not cfg_path.exists():
        return None
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    plc_endpoints = (
        raw.get("workers", {})
        .get("configs", {})
        .get("twincat", {})
        .get("plc_endpoints", [])
    )
    if not isinstance(plc_endpoints, list) or not plc_endpoints:
        return None

    selected: dict[str, Any] | None = None
    for ep in plc_endpoints:
        if not isinstance(ep, dict):
            continue
        if str(ep.get("client_id", "")) == "Beckhoff-PLC":
            selected = ep
            break
        if selected is None:
            selected = ep
    if selected is None:
        return None
    return {
        "client_id": str(selected.get("client_id") or ""),
        "plc_ip": str(selected.get("plc_ip") or ""),
        "subscriptions": list(selected.get("subscriptions", []) or []),
    }


def _load_specs(endpoint: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not endpoint:
        return []
    out: list[dict[str, Any]] = []
    for item in endpoint.get("subscriptions", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        alias = str(item.get("alias") or "").strip()
        plc_type = str(item.get("plc_type") or "STRING(80)").strip()
        string_len = int(item.get("string_len", 80) or 80)
        writable = _is_writable(alias, name)
        out.append(
            {
                "id": f"{alias or name}",
                "alias": alias,
                "name": name,
                "plc_type": plc_type,
                "string_len": string_len,
                "writable": writable,
            }
        )
    return out


def _group_specs(specs: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order = [
        "Stepchain / Core",
        "MES Handshake",
        "Part Result",
        "Simple IO",
        "Wenglor Sensors",
        "Fixture",
        "Cameras / Profinet",
        "Other",
    ]
    for spec in specs:
        key = _group_name(str(spec.get("name") or ""), str(spec.get("alias") or ""))
        grouped.setdefault(key, []).append(spec)
    out: list[tuple[str, list[dict[str, Any]]]] = []
    for name in order:
        items = grouped.get(name, [])
        if items:
            out.append((name, items))
    return out


def _group_name(symbol_name: str, alias: str) -> str:
    name = f"{symbol_name} {alias}"
    if "ZenonMes" in name:
        return "MES Handshake"
    if "resultArray" in name or alias.startswith("Part_Result"):
        return "Part Result"
    if "SimpleIos" in name or alias in ("Working_Light", "Insight_Light", "Ring_Light", "Bad_Rail", "IS_Gen3"):
        return "Simple IO"
    if "Wenglor" in name:
        return "Wenglor Sensors"
    if "Fixture" in name:
        return "Fixture"
    if "DMCReader" in name or "Insight" in name or "Camera" in alias or "Profinet" in alias:
        return "Cameras / Profinet"
    if "zenonVisu" in name or alias in ("watchdog", "update_view", "Step", "ErrorText", "StepText", "stop"):
        return "Stepchain / Core"
    return "Other"


def _is_writable(alias: str, symbol_name: str) -> bool:
    if alias in KNOWN_WRITABLE_ALIASES:
        return True
    if ".Set_" in symbol_name:
        return True
    if alias.startswith("Set_"):
        return True
    return False


def _editor_kind(plc_type: str) -> str:
    pt = str(plc_type or "").upper().strip()
    if pt.startswith("BOOL"):
        return "bool"
    if pt in ("SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT", "WORD", "DWORD", "LWORD", "BYTE", "REAL", "LREAL"):
        return "number"
    return "text"


def _coerce_value(value: Any, plc_type: str) -> Any:
    pt = str(plc_type or "").upper().strip()
    if pt.startswith("BOOL"):
        return bool(value)
    if pt in ("SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT", "WORD", "DWORD", "LWORD", "BYTE"):
        return int(value)
    if pt in ("REAL", "LREAL"):
        return float(value)
    return "" if value is None else str(value)


def _load_current_into_editor(spec: dict[str, Any], editor: Any, runtime_values: dict[str, Any]) -> None:
    value = _current_value(spec, runtime_values)
    pt = str(spec.get("plc_type") or "")
    try:
        editor.value = _coerce_value(value, pt)
    except Exception:
        editor.value = value


def _current_value(spec: dict[str, Any], runtime_values: dict[str, Any]) -> Any:
    alias = str(spec.get("alias") or "")
    name = str(spec.get("name") or "")
    if alias and alias in runtime_values:
        return runtime_values.get(alias)
    if name and name in runtime_values:
        return runtime_values.get(name)
    return None


def _to_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)

