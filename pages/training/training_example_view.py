from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.worker_topics import WorkerTopics

VIEW_ID = "training_example_view"
TCP_SOURCE = "tcp_client"
TCP_SOURCE_ID = "training_scanner"
CSV_PATH = Path("training/output/training_scans.csv")


BUTTONS: dict[str, str] = {
    "btn_a": "Action A",
    "btn_b": "Action B",
    "show_popup": "Show Popup",
    "ask_confirm": "Ask Confirm",
    "write_csv": "Write CSV row",
    "reset_state": "Reset state",
}


def _now_event_id() -> int:
    return int(time.time() * 1000)


def _safe_text(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def render(container: ui.element, ctx: PageContext) -> None:
    page_timers: list[Any] = []

    scan_input_ref: dict[str, Any] = {"input": None}
    state_table_ref: dict[str, Any] = {"table": None}

    def add_timer(*args, **kwargs):
        timer = ui.timer(*args, **kwargs)
        page_timers.append(timer)
        return timer

    def cleanup() -> None:
        for timer in page_timers:
            try:
                timer.cancel()
            except Exception:
                pass
        page_timers[:] = []

    ctx.state._page_cleanup = cleanup
    ui.context.client.on_disconnect(cleanup)

    def set_training_state(key: str, value: Any) -> None:
        ctx.set_state_and_publish(key, value)

    def get_training_state(key: str, default: Any = None) -> Any:
        return getattr(ctx.state, key, default)

    def publish_command(action: str, extra: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            "event_id": _now_event_id(),
            "action": str(action),
            "view": VIEW_ID,
            "ts": time.time(),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        set_training_state("training_command", payload)

    def publish_tcp_scan(code: str) -> None:
        value = str(code or "").strip()
        if not value:
            ui.notify("Please enter a scan code first.", type="warning")
            return
        ctx.worker_bus.publish(
            topic=WorkerTopics.VALUE_CHANGED,
            source=TCP_SOURCE,
            source_id=TCP_SOURCE_ID,
            key="message",
            value=value,
        )
        set_training_state("training_last_simulated_scan", value)
        ui.notify(f"Simulated TCP scan sent: {value}", type="positive")

    def state_rows() -> list[dict[str, str]]:
        keys = [
            "training_active_script",
            "training_status",
            "training_mode",
            "training_last_scan",
            "training_scan_count",
            "training_confirm_result",
            "training_csv_count",
            "training_csv_last_status",
            "training_csv_path",
            "training_last_button",
            "training_last_simulated_scan",
            "view_button_states",
        ]
        return [{"key": key, "value": _safe_text(get_training_state(key, "-"))} for key in keys]

    def refresh_state_table() -> None:
        table = state_table_ref.get("table")
        if table is None:
            return
        table.rows = state_rows()
        table.update()

    def is_button_enabled(key: str) -> bool:
        map_raw = get_training_state("view_button_states", {})
        state_map = dict(map_raw) if isinstance(map_raw, dict) else {}
        full_key = f"{VIEW_ID}.{key}"
        return bool(state_map.get(full_key, True))

    def render_button_row() -> None:
        with ui.row().classes("w-full gap-2"):
            for key, label in BUTTONS.items():
                ui.button(
                    label,
                    on_click=lambda _=None, k=key: publish_command(k, {"button_key": k}),
                ).props("unelevated color=primary").bind_enabled_from(
                    ctx.state,
                    "view_button_states",
                    backward=lambda raw, button_key=key: bool(
                        (raw or {}).get(f"{VIEW_ID}.{button_key}", True)
                    ) if isinstance(raw, dict) else True,
                )

    def build_content(_: ui.element) -> None:
        with ui.column().classes("w-full gap-3"):
            ui.label("Training Example View").classes("text-xl font-bold")
            ui.label(
                "Use this page with scripts/training/training_example_view_1.py or _2.py. "
                "Buttons publish events into AppState; scripts react and update this page."
            ).classes("text-sm text-gray-600")

            with ui.card().classes("w-full p-3 gap-3"):
                ui.label("Buttons controlled by script").classes("text-base font-semibold")
                render_button_row()

                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Mode:").classes("text-sm font-medium")
                    ui.select(
                        options={"standard": "standard", "strict": "strict", "relaxed": "relaxed"},
                        value=get_training_state("training_mode", "standard"),
                        on_change=lambda e: set_training_state("training_mode", str(getattr(e, "value", "standard"))),
                    ).props("outlined dense").classes("w-48")

            with ui.card().classes("w-full p-3 gap-2"):
                ui.label("Scan input (TCP simulation)").classes("text-base font-semibold")
                ui.label(
                    "Enter a code and click 'Simulate incoming scan'. "
                    "This publishes the same tcp_client/message bus event used by real scanners."
                ).classes("text-xs text-gray-600")
                with ui.row().classes("w-full items-center gap-2"):
                    scan_input_ref["input"] = ui.input("Scan code", value="TRN-10001").classes("w-80")
                    ui.button(
                        "Simulate incoming scan",
                        icon="qr_code_scanner",
                        on_click=lambda: publish_tcp_scan(getattr(scan_input_ref["input"], "value", "")),
                    ).props("unelevated color=secondary")

            with ui.card().classes("w-full p-3 gap-2"):
                ui.label("CSV output").classes("text-base font-semibold")
                ui.label(f"File: {CSV_PATH.as_posix()}").classes("text-xs text-gray-600")
                ui.label("Use the 'Write CSV row' button above to append a line.").classes("text-xs text-gray-600")

            with ui.card().classes("w-full p-3"):
                ui.label("Live training state").classes("text-base font-semibold")
                table = ui.table(
                    columns=[
                        {"name": "key", "label": "Key", "field": "key", "align": "left"},
                        {"name": "value", "label": "Value", "field": "value", "align": "left"},
                    ],
                    rows=state_rows(),
                    row_key="key",
                    pagination={"rowsPerPage": 15},
                ).classes("w-full text-xs")
                table.props("dense bordered flat")
                state_table_ref["table"] = table

    build_page(
        ctx,
        container,
        title="Training Example",
        content=build_content,
        show_action_bar=False,
    )

    add_timer(0.5, refresh_state_table)

