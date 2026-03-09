from __future__ import annotations

import queue
from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.app_config import get_app_config, get_twincat_plc_endpoints
from services.route_settings import get_route_settings
from services.worker_topics import WorkerTopics
from ui.components import page_container, panel


def render(container: ui.element, ctx: PageContext) -> None:
    route_settings = get_route_settings(ctx.current_route_key or "pack_nox_status")
    endpoint = _pick_endpoint(route_settings.get("plc_endpoint"))
    runtime_values: dict[str, Any] = {}

    sub = ctx.worker_bus.subscribe_many([WorkerTopics.VALUE_CHANGED]) if endpoint and ctx.worker_bus else None

    def _drain() -> None:
        if sub is None:
            return
        while True:
            try:
                msg = sub.queue.get_nowait()
            except queue.Empty:
                break
            payload = getattr(msg, "payload", {}) or {}
            key = str(payload.get("key") or "")
            if key:
                runtime_values[key] = payload.get("value")

    ui.timer(0.2, _drain)

    def _content(_parent: ui.element) -> None:
        with page_container():
            with panel("Packaging NOX Status", "TwinCAT runtime values", icon="ti-heartbeat"):
                ui.label(f"PLC worker: {route_settings.get('plc_worker', '-')}").classes("text-sm text-muted")
                ui.label(f"PLC endpoint: {endpoint.get('client_id', '-') if endpoint else '-'}").classes("text-sm text-muted")
                for item in (endpoint.get("subscriptions", []) if endpoint else []):
                    name = str(item.get("alias") or item.get("name") or "")
                    value_label = ui.label("-").classes("text-sm")
                    ui.timer(0.4, lambda n=name, lbl=value_label: lbl.set_text(f"{n}: {runtime_values.get(n, '-')}") )

    build_page(ctx, container, title="Packaging NOX Status", content=_content, show_action_bar=False)


def _pick_endpoint(preferred_id: str | None) -> dict[str, Any] | None:
    cfg = get_app_config()
    endpoints = get_twincat_plc_endpoints(cfg)
    if not endpoints:
        return None
    if preferred_id:
        for endpoint in endpoints:
            if str(getattr(endpoint, "client_id", "")) == str(preferred_id):
                return {
                    "client_id": str(getattr(endpoint, "client_id", "")),
                    "subscriptions": list(getattr(endpoint, "subscriptions", []) or []),
                }
    first = endpoints[0]
    return {
        "client_id": str(getattr(first, "client_id", "")),
        "subscriptions": list(getattr(first, "subscriptions", []) or []),
    }
