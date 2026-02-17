from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_app_config
from services.worker_topics import WorkerTopics


def _now_ts() -> float:
    return time.time()


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "-"


def _expected_endpoints(cfg) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    workers = cfg.workers.configs

    def add(worker: str, source_id: str, label: str) -> None:
        out.append({"worker": worker, "source_id": source_id, "label": label})

    for ep in workers.get("twincat", {}).get("plc_endpoints", []) or []:
        add("twincat", str(ep.get("client_id", "")), "TwinCAT PLC")

    for ep in workers.get("opcua", {}).get("endpoints", []) or []:
        add("opcua", str(ep.get("name", "")), "OPC UA")

    for ep in workers.get("tcp_client", {}).get("clients", []) or []:
        add("tcp_client", str(ep.get("client_id", "")), "TCP Client")

    for ep in workers.get("rest_api", {}).get("endpoints", []) or []:
        add("rest_api", str(ep.get("name", "")), "REST API")

    for ep in workers.get("itac", {}).get("endpoints", []) or []:
        add("itac", str(ep.get("name", "")), "iTAC")

    for ep in workers.get("com_device", {}).get("devices", []) or []:
        dev_id = ep.get("device_id") or ep.get("id") or ""
        add("com_device", str(dev_id), "COM Device")

    return out


def render(container: ui.element, ctx: PageContext) -> None:
    with container.classes("w-full h-full min-h-0 overflow-hidden"):
        with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col gap-2"):
            ui.label("Online Status").classes("text-2xl font-bold")
            ui.label("Live connection status for configured workers.").classes("text-sm text-gray-500")

            columns = [
                {"name": "worker", "label": "Worker", "field": "worker", "align": "left"},
                {"name": "source_id", "label": "Source ID", "field": "source_id", "align": "left"},
                {"name": "label", "label": "Type", "field": "label", "align": "left"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "last_change", "label": "Last Change", "field": "last_change", "align": "left"},
                {"name": "reason", "label": "Reason", "field": "reason", "align": "left"},
            ]

            table = ui.table(columns=columns, rows=[], row_key="key") \
                .classes("w-full flex-1") \
                .props("dense separator=cell")

            status_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

            sub = None
            try:
                if ctx.worker_bus is not None:
                    sub = ctx.worker_bus.subscribe_many([
                        WorkerTopics.CLIENT_CONNECTED,
                        WorkerTopics.CLIENT_DISCONNECTED,
                        WorkerTopics.ERROR,
                        WorkerTopics.VALUE_CHANGED,
                    ])
            except Exception:
                sub = None

            def _set_status(key: Tuple[str, str], status: str, reason: str = "") -> None:
                status_map[key] = {
                    "status": status,
                    "reason": reason,
                    "ts": _now_ts(),
                }

            def _drain() -> None:
                if sub is None:
                    return
                while True:
                    try:
                        msg = sub.queue.get_nowait()
                    except Exception:
                        break
                    worker = str(getattr(msg, "source", "") or "")
                    source_id = str(getattr(msg, "source_id", "") or "")
                    key = (worker, source_id)
                    if msg.topic == str(getattr(WorkerTopics.CLIENT_CONNECTED, "value", WorkerTopics.CLIENT_CONNECTED)):
                        _set_status(key, "connected", "")
                    elif msg.topic == str(getattr(WorkerTopics.CLIENT_DISCONNECTED, "value", WorkerTopics.CLIENT_DISCONNECTED)):
                        reason = str((msg.payload or {}).get("reason", "") or "")
                        _set_status(key, "disconnected", reason)
                    elif msg.topic == str(getattr(WorkerTopics.ERROR, "value", WorkerTopics.ERROR)):
                        err = str((msg.payload or {}).get("error", "") or "")
                        action = str((msg.payload or {}).get("action", "") or "")
                        reason = err or action or "error"
                        _set_status(key, "error", reason)
                    elif msg.topic == str(getattr(WorkerTopics.VALUE_CHANGED, "value", WorkerTopics.VALUE_CHANGED)):
                        payload = getattr(msg, "payload", None) or {}
                        k = str(payload.get("key") or "")
                        v = payload.get("value")

                        # REST API results: rest.<endpoint>.result.<id>
                        if worker == "rest_api" and k.startswith("rest.%s.result." % source_id):
                            ok = False
                            if isinstance(v, dict):
                                ok = bool(v.get("ok", False))
                                reason = str(v.get("error", "") or v.get("status", "") or "")
                            else:
                                reason = ""
                            _set_status(key, "connected" if ok else "error", reason)

                        # iTAC results: itac.<connection_id>.*
                        if worker == "itac" and k.startswith("itac.%s." % source_id):
                            if isinstance(v, dict) and v.get("error"):
                                _set_status(key, "error", str(v.get("error")))
                            else:
                                _set_status(key, "connected", "")

            def _build_rows() -> List[Dict[str, str]]:
                cfg = get_app_config()
                expected = _expected_endpoints(cfg)
                enabled_workers = set(cfg.workers.enabled_workers or [])

                rows: List[Dict[str, str]] = []
                seen: set[Tuple[str, str]] = set()

                for ep in expected:
                    worker = ep.get("worker", "")
                    source_id = ep.get("source_id", "")
                    seen.add((worker, source_id))
                    st = status_map.get((worker, source_id), {})
                    running = bool(ctx.workers and ctx.workers.is_running(worker))
                    status = st.get("status")
                    if not status:
                        if worker in enabled_workers and running:
                            status = "idle"
                        elif worker in enabled_workers:
                            status = "starting"
                        else:
                            status = "disabled"
                    reason = st.get("reason", "")
                    ts = _fmt_ts(st.get("ts"))
                    icon = {
                        "connected": "🟢",
                        "disconnected": "🔴",
                        "error": "🟥",
                        "idle": "🟡",
                        "starting": "⚪",
                        "disabled": "⚫",
                    }.get(status, "⚪")
                    rows.append({
                        "key": f"{worker}:{source_id}",
                        "worker": worker,
                        "source_id": source_id,
                        "label": ep.get("label", ""),
                        "status": f"{icon} {status}",
                        "last_change": ts,
                        "reason": reason,
                    })

                # include any dynamic endpoints seen on the bus but not in config
                for (worker, source_id), st in status_map.items():
                    if (worker, source_id) in seen:
                        continue
                    rows.append({
                        "key": f"{worker}:{source_id}",
                        "worker": worker,
                        "source_id": source_id,
                        "label": "Runtime",
                        "status": f"⚪ {st.get('status', 'unknown')}",
                        "last_change": _fmt_ts(st.get("ts")),
                        "reason": st.get("reason", ""),
                    })

                rows.sort(key=lambda r: (r["worker"], r["source_id"]))
                return rows

            last_snapshot: list[dict[str, str]] = []

            def refresh(force: bool = False) -> None:
                _drain()
                rows = _build_rows()
                if not force and rows == last_snapshot:
                    return
                last_snapshot.clear()
                last_snapshot.extend(rows)
                table.rows = rows
                table.update()

            ui.timer(0.2, lambda: refresh(False))
            refresh(True)
