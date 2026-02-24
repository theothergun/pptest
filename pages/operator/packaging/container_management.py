from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from nicegui import ui
from layout.context import PageContext
from services.i18n import t
from loguru import logger
from services.ui.view_action import publish_standard_view_action
from services.ui.view_cmd import install_wait_dialog, view_wait_key


CONTAINER_MGMT_CMD_KEY = "container_management.cmd"
CONTAINER_MGMT_VIEW = "container_management"
CONTAINER_MGMT_WAIT_MODAL_KEY = view_wait_key(CONTAINER_MGMT_VIEW)


def render(container: ui.element, ctx: PageContext) -> None:
    logger.debug("[render] - page_render - page=container_management")
    container.style("overflow-y: auto !important; overflow-x: hidden !important;")
    with container:
        build_page(ctx)


def build_page(ctx: PageContext) -> None:
    worker_bus = ctx.workers.worker_bus
    page_timers: list = []

    ui.add_head_html(
        """
<style>
.cm-shell {
    background: linear-gradient(135deg, var(--surface-muted) 0%, var(--app-background) 100%);
    border-radius: 20px;
    border: 1px solid var(--input-border);
    box-shadow: 0 12px 30px rgba(16, 24, 40, 0.06);
}
.cm-card {
    border: 1px solid var(--input-border);
    border-radius: 16px;
    box-shadow: 0 10px 24px rgba(16, 24, 40, 0.08);
    background: var(--surface);
    color: var(--text-primary);
    overflow: hidden;
}
.cm-panel {
    background: linear-gradient(180deg, var(--surface-muted) 0%, var(--surface) 100%);
    border: 1px solid var(--input-border);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}
.cm-title {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--primary);
    font-weight: 700;
}
.cm-btn {
    font-weight: 700;
    letter-spacing: 0.25px;
    border-radius: 12px;
    transition: transform 120ms ease, box-shadow 120ms ease;
}
.cm-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.14);
}
.cm-table {
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid var(--input-border);
}
.cm-table .q-table__top,
.cm-table .q-table__bottom {
    background: var(--surface-muted);
}
.cm-table thead tr {
    background: color-mix(in srgb, var(--surface-muted) 82%, var(--primary) 18%);
}
.cm-table thead th {
    font-weight: 700;
    color: var(--text-primary);
    border-bottom: 1px solid var(--input-border);
}
.cm-table tbody tr:nth-child(even) {
    background: color-mix(in srgb, var(--surface) 88%, var(--surface-muted) 12%);
}
.cm-table tbody tr:hover {
    background: color-mix(in srgb, var(--primary) 12%, var(--surface) 88%) !important;
}
.cm-section-scroll {
    max-height: 34vh;
    overflow: auto;
}
.cm-chip {
    border-radius: 12px;
    border: 1px solid var(--input-border);
    background: var(--surface-muted);
}
</style>
"""
    )

    def add_timer(*args, **kwargs):
        timer = ui.timer(*args, **kwargs)
        page_timers.append(timer)
        return timer

    def cleanup() -> None:
        for sub in wait_dialog["subs"]:
            try:
                sub.close()
            except Exception:
                pass
        for timer in page_timers:
            try:
                timer.cancel()
            except Exception:
                pass
        page_timers[:] = []

    ctx.state._page_cleanup = cleanup
    ui.context.client.on_disconnect(cleanup)

    wait_dialog = install_wait_dialog(
        ctx=ctx,
        worker_bus=worker_bus,
        wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
        title=t("packaging.wait_title", "Please wait"),
        message=t("packaging.working", "Working ..."),
        add_timer=add_timer,
    )

    def _publish_cmd(cmd: str) -> None:
        publish_standard_view_action(
            worker_bus=worker_bus,
            view=CONTAINER_MGMT_VIEW,
            cmd_key=CONTAINER_MGMT_CMD_KEY,
            name=cmd,
            event="click",
            wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
            open_wait=wait_dialog["open"],
            source_id=CONTAINER_MGMT_VIEW,
        )

    def _publish_cmd_payload(cmd: str, **extra: Any) -> None:
        publish_standard_view_action(
            worker_bus=worker_bus,
            view=CONTAINER_MGMT_VIEW,
            cmd_key=CONTAINER_MGMT_CMD_KEY,
            name=cmd,
            event="click",
            wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
            open_wait=wait_dialog["open"],
            extra=extra,
            source_id=CONTAINER_MGMT_VIEW,
        )

    def _label(key: str, fallback: str) -> str:
        # Some translations currently contain a leading '@'; hide it in the UI.
        return str(t(key, fallback) or fallback).lstrip("@").strip()

    def _refresh_tables() -> None:
        container_rows = list(getattr(ctx.state, "container_mgmt_container_rows", []) or [])
        serial_rows = list(getattr(ctx.state, "container_mgmt_serial_rows", []) or [])

        table_containers.rows = container_rows
        table_serials.rows = serial_rows

        table_containers.update()
        table_serials.update()

    def _extract_clicked_row(args: Any) -> dict[str, Any] | None:
        try:
            if isinstance(args, dict):
                return args
            if isinstance(args, (list, tuple)):
                for item in args:
                    if isinstance(item, dict) and "serial_number" in item:
                        return item
            return None
        except Exception:
            return None

    selected_serial: dict[str, str] = {"value": ""}

    with ui.column().classes("cm-shell w-full h-full flex flex-col min-h-0 overflow-y-auto overflow-x-hidden p-3 gap-3"):
        with ui.row().classes("w-full items-center gap-2 cm-card px-3 py-2"):
            ui.icon("inventory_2").classes("text-xl text-amber-500")
            with ui.column().classes("gap-0"):
                ui.label(t("container_management.title", "Container Management")).classes("text-lg font-bold")
                ui.label(t("container_management.subtitle", "Search, activate, and maintain container serials")).classes("text-[11px] text-gray-500")
            ui.space()
            with ui.row().classes("items-center gap-2 cm-chip px-3 py-2"):
                ui.icon("inventory").classes("text-primary")
                ui.label(t("container_management.active_container", "Active Container:")).classes("text-xs text-gray-500")
                ui.label("").classes("font-bold") \
                    .bind_text_from(ctx.state, "container_mgmt_active_container", backward=lambda n: str(n or "-"))

        with ui.card().classes("cm-card cm-panel p-3 w-full"):
            ui.label(t("container_management.search_container", "Search Container")).classes("cm-title")
            with ui.row().classes("w-full gap-2 items-end mt-1"):
                ui.input(t("common.search", "Search")).classes("w-full app-input") \
                    .bind_value_from(ctx.state, "container_mgmt_search_query", backward=lambda n: str(n or ""))

        with ui.card().classes("cm-card p-3 w-full"):
            with ui.row().classes("w-full items-center mb-2"):
                ui.label(t("container_management.container_results", "Container Results")).classes("text-sm font-bold")
                ui.space()
                ui.icon("table_view").classes("text-primary")

            with ui.row().classes("w-full gap-3 items-start"):
                with ui.column().classes("flex-1 min-w-0"):
                    container_columns = [
                        {"name": "material_bin", "label": "MATERIAL_BIN", "field": "material_bin", "align": "left", "sortable": True},
                        {"name": "part_number", "label": "Partnumber", "field": "part_number", "align": "left", "sortable": True},
                        {"name": "current_qty", "label": "Current Qty", "field": "current_qty", "align": "center", "sortable": True},
                    ]
                    with ui.column().classes("cm-section-scroll w-full"):
                        table_containers = ui.table(
                            columns=container_columns,
                            rows=[],
                            row_key="material_bin",
                            pagination={"rowsPerPage": 6},
                        ).classes("cm-table w-full text-sm")
                        table_containers.props("dense bordered flat separator=horizontal rows-per-page-options=[6,8,12,25,50]")

                with ui.column().classes("w-full lg:w-[340px] lg:min-w-[340px] gap-2"):
                    ui.button(
                        _label("container_management.search_by_container", "Search by container"),
                        on_click=lambda: _publish_cmd("search_container"),
                        icon="inventory",
                    ).props("color=primary text-color=white").classes("w-full h-[42px] cm-btn text-white")
                    ui.button(
                        _label("container_management.search_by_serial", "Search by Serialnumber"),
                        on_click=lambda: _publish_cmd("search_serial"),
                        icon="qr_code_scanner",
                    ).props("color=secondary text-color=white").classes("w-full h-[42px] cm-btn text-white")
                    ui.button(
                        _label("container_management.activate", "Activate"),
                        on_click=lambda: _publish_cmd("activate"),
                        icon="bolt",
                    ).props("color=positive text-color=white").classes("w-full h-[42px] cm-btn text-white")

        with ui.card().classes("cm-card p-3 w-full"):
            with ui.row().classes("w-full items-center mb-2"):
                ui.label(t("container_management.serials", "Container Serials")).classes("text-sm font-bold")
                ui.space()
                ui.icon("numbers").classes("text-primary")

            with ui.row().classes("w-full gap-3 items-start"):
                with ui.column().classes("flex-1 min-w-0"):
                    serial_columns = [
                        {"name": "serial_number", "label": "Serialnumber", "field": "serial_number", "align": "left", "sortable": True},
                        {"name": "created_on", "label": "Created on", "field": "created_on", "align": "left", "sortable": True},
                    ]
                    with ui.column().classes("cm-section-scroll w-full"):
                        table_serials = ui.table(
                            columns=serial_columns,
                            rows=[],
                            row_key="serial_number",
                            pagination={"rowsPerPage": 6},
                        ).classes("cm-table w-full text-sm")
                        table_serials.props("dense bordered flat separator=horizontal rows-per-page-options=[6,8,12,25,50]")

                with ui.card().classes("cm-card cm-panel p-3 w-full lg:w-[340px] lg:min-w-[340px] self-start"):
                    ui.label(t("container_management.actions", "Actions")).classes("cm-title")
                    ui.label("").classes("text-sm font-semibold text-gray-600") \
                        .bind_text_from(
                            ctx.state,
                            "container_mgmt_container_selected",
                            backward=lambda n: t("container_management.selected", "Selected: {value}", value=str(n or "-")),
                        )

                    with ui.column().classes("w-full gap-2 mt-2"):
                        ui.button(t("common.search", "Search"), on_click=lambda: _publish_cmd("search"), icon="search") \
                            .props("color=primary text-color=white").classes("w-full h-[42px] cm-btn text-white")
                        ui.button(t("common.refresh", "Refresh"), on_click=lambda: _publish_cmd("refresh"), icon="refresh") \
                            .props("color=secondary text-color=white").classes("w-full h-[42px] cm-btn text-white")
                        ui.button(
                            _label("container_management.remove_serial", "Remove Serial"),
                            on_click=lambda: _publish_cmd_payload("remove_serial", serial=selected_serial.get("value", "")),
                            icon="remove_circle",
                        ).props("color=warning text-color=white").classes("w-full h-[42px] cm-btn text-white")
                        ui.button(
                            _label("container_management.remove_all", "Remove All"),
                            on_click=lambda: _publish_cmd("remove_all"),
                            icon="delete_forever",
                        ).props("color=negative text-color=white").classes("w-full h-[42px] cm-btn text-white")

                    selected_serial_label = ui.label(
                        t("container_management.selected_serial", "Selected serial: {value}", value="-")
                    ).classes("text-xs text-gray-500")

            def _on_serial_click(e: Any) -> None:
                row = _extract_clicked_row(getattr(e, "args", None))
                if row is None:
                    return
                selected_serial["value"] = str(row.get("serial_number", "") or "")
                selected_serial_label.set_text(
                    t("container_management.selected_serial", "Selected serial: {value}", value=selected_serial["value"])
                )

            table_serials.on("rowClick", _on_serial_click)

    add_timer(0.2, _refresh_tables)
