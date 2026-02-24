from __future__ import annotations

from datetime import datetime
from typing import Any

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page


STATUS_KEYS: dict[str, Any] = {
    # Fixture / Camera
    "pnxs_fixture_camera_online": False,
    "pnxs_fixture_camera_busy": False,
    "pnxs_fixture_camera_job_id": "",
    "pnxs_fixture_camera_result_ok": False,
    "pnxs_fixture_profinet_state": "UNKNOWN",
    # PLC / field state
    "pnxs_plc_connected": False,
    "pnxs_profinet_device_ready": False,
    "pnxs_safety_ok": False,
    "pnxs_cycle_running": False,
    # Diagnostic metadata
    "pnxs_last_update_ts": "-",
    "pnxs_note": "",
}


def render(container: ui.element, ctx: PageContext) -> None:
    _ensure_runtime_defaults(ctx)

    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full h-full min-h-0 flex flex-col gap-3"):
            with ui.card().classes("w-full p-3"):
                ui.label("Packaging NOX Status").classes("text-xl font-bold")
                ui.label(
                    "Engineer status dashboard for relevant IOs. "
                    "All keys are runtime keys (`pnxs_*`) and not part of default AppState."
                ).classes("text-sm text-gray-500")

            with ui.row().classes("w-full gap-3 items-stretch"):
                with ui.card().classes("w-[380px] max-w-full p-3"):
                    ui.label("Fixture / Camera").classes("text-sm font-semibold")
                    _bool_row("Camera Online", ctx, "pnxs_fixture_camera_online")
                    _bool_row("Camera Busy", ctx, "pnxs_fixture_camera_busy")
                    _text_row("Camera Job ID", ctx, "pnxs_fixture_camera_job_id")
                    _bool_row("Camera Result OK", ctx, "pnxs_fixture_camera_result_ok")
                    _text_row("Profinet State", ctx, "pnxs_fixture_profinet_state")

                with ui.card().classes("w-[380px] max-w-full p-3"):
                    ui.label("PLC / Cell").classes("text-sm font-semibold")
                    _bool_row("PLC Connected", ctx, "pnxs_plc_connected")
                    _bool_row("Profinet Device Ready", ctx, "pnxs_profinet_device_ready")
                    _bool_row("Safety OK", ctx, "pnxs_safety_ok")
                    _bool_row("Cycle Running", ctx, "pnxs_cycle_running")
                    _text_row("Last Update", ctx, "pnxs_last_update_ts")

                with ui.card().classes("grow min-w-[320px] p-3"):
                    ui.label("Quick Actions (sample)").classes("text-sm font-semibold")
                    ui.label(
                        "Use these sample actions to test bindings. "
                        "In production, your worker/stepchain can write the same keys."
                    ).classes("text-xs text-gray-500")
                    with ui.row().classes("w-full gap-2 mt-2"):
                        ui.button(
                            "Set Online",
                            on_click=lambda: _set_many(
                                ctx,
                                pnxs_fixture_camera_online=True,
                                pnxs_plc_connected=True,
                                pnxs_last_update_ts=_now(),
                            ),
                        ).props("color=positive")
                        ui.button(
                            "Set Busy",
                            on_click=lambda: _set_many(
                                ctx,
                                pnxs_fixture_camera_busy=True,
                                pnxs_cycle_running=True,
                                pnxs_fixture_profinet_state="RUNNING",
                                pnxs_last_update_ts=_now(),
                            ),
                        ).props("color=warning")
                        ui.button(
                            "Set Offline",
                            on_click=lambda: _set_many(
                                ctx,
                                pnxs_fixture_camera_online=False,
                                pnxs_plc_connected=False,
                                pnxs_fixture_camera_busy=False,
                                pnxs_cycle_running=False,
                                pnxs_fixture_profinet_state="OFFLINE",
                                pnxs_last_update_ts=_now(),
                            ),
                        ).props("color=negative")
                    note_input = ui.input("Engineer Note").classes("w-full mt-3")
                    ui.button(
                        "Apply Note",
                        on_click=lambda: _set_many(ctx, pnxs_note=str(note_input.value or ""), pnxs_last_update_ts=_now()),
                    ).props("outline")
                    ui.label("").classes("text-xs text-gray-600 mt-2").bind_text_from(
                        ctx.state,
                        "pnxs_note",
                        backward=lambda v: f"Current note: {v or '-'}",
                    )

            with ui.card().classes("w-full flex-1 min-h-0 p-3 flex flex-col"):
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("Runtime State (`pnxs_*`)").classes("text-sm font-semibold")
                    ui.space()
                    filter_input = ui.input("Filter keys", placeholder="e.g. camera").props("dense clearable").classes("w-[280px]")
                    ui.button("Refresh", on_click=lambda: table_refresh.refresh()).props("flat")

                @ui.refreshable
                def table_refresh() -> None:
                    rows = _collect_runtime_rows(ctx, str(filter_input.value or "").strip().lower())
                    columns = [
                        {"name": "key", "label": "Key", "field": "key", "align": "left"},
                        {"name": "value", "label": "Value", "field": "value", "align": "left"},
                        {"name": "type", "label": "Type", "field": "type", "align": "left"},
                    ]
                    with ui.element("div").classes("w-full flex-1 min-h-0 overflow-auto"):
                        ui.table(columns=columns, rows=rows, row_key="key").props("dense flat separator=cell").classes("w-full")

                ui.timer(0.5, table_refresh.refresh)
                table_refresh()

    build_page(
        ctx,
        container,
        title="Packaging NOX Status",
        content=build_content,
        show_action_bar=False,
    )


def _set_many(ctx: PageContext, **values: Any) -> None:
    for key, value in values.items():
        try:
            ctx.set_state_and_publish(str(key), value)
        except Exception:
            setattr(ctx.state, str(key), value)


def _ensure_runtime_defaults(ctx: PageContext) -> None:
    updates: dict[str, Any] = {}
    for key, default in STATUS_KEYS.items():
        if not hasattr(ctx.state, key):
            setattr(ctx.state, key, default)
            updates[key] = default
    # Publish once so other subscribers can see initial runtime keys too.
    for key, value in updates.items():
        try:
            ctx.bridge.emit_patch(key, value)
        except Exception:
            pass


def _collect_runtime_rows(ctx: PageContext, query: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    state_dict = getattr(ctx.state, "__dict__", {})
    for key in sorted(state_dict.keys()):
        if not str(key).startswith("pnxs_"):
            continue
        value = state_dict.get(key)
        key_s = str(key)
        val_s = _to_text(value)
        if query and query not in key_s.lower() and query not in val_s.lower():
            continue
        out.append({"key": key_s, "value": val_s, "type": type(value).__name__})
    return out


def _to_text(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _bool_row(label: str, ctx: PageContext, key: str) -> None:
    with ui.row().classes("w-full items-center justify-between py-1"):
        ui.label(label).classes("text-sm")
        badge = ui.badge("-").props("text-color=white")

        def _apply(v: Any) -> None:
            state = bool(v)
            badge.set_text("ON" if state else "OFF")
            badge.props(f"color={'positive' if state else 'negative'}")

        _apply(getattr(ctx.state, key, False))
        ui.timer(0.3, lambda: _apply(getattr(ctx.state, key, False)))


def _text_row(label: str, ctx: PageContext, key: str) -> None:
    with ui.row().classes("w-full items-center justify-between py-1"):
        ui.label(label).classes("text-sm")
        ui.label("-").classes("text-sm font-mono").bind_text_from(ctx.state, key, backward=lambda v: str(v or "-"))

