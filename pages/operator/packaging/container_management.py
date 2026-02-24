from __future__ import annotations

from typing import Any

from nicegui import ui

from layout.context import PageContext
from loguru import logger
from services.i18n import t
from services.ui.view_action import publish_standard_view_action
from services.ui.view_cmd import install_wait_dialog
from services.ui.registry import UiActionName, UiEvent, ViewName, view_wait_key


CONTAINER_MGMT_CMD_KEY = "container_management.cmd"
CONTAINER_MGMT_VIEW = ViewName.CONTAINER_MANAGEMENT
CONTAINER_MGMT_WAIT_MODAL_KEY = view_wait_key(CONTAINER_MGMT_VIEW)


def render(container: ui.element, ctx: PageContext) -> None:
    logger.debug("[render] - page_render - page=container_management")
    container.style("overflow: auto !important; min-height: 0 !important;")
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
    border-radius: 16px;
    border: 1px solid var(--input-border);
    box-shadow: 0 8px 18px rgba(16, 24, 40, 0.06);
}
.cm-card {
    border: 1px solid var(--input-border);
    border-radius: 12px;
    background: var(--surface);
    color: var(--text-primary);
    overflow: hidden;
}
.cm-title {
    font-size: 12px;
    font-weight: 700;
}
.cm-chip {
    border-radius: 10px;
    border: 1px solid var(--input-border);
    background: var(--surface-muted);
}
.cm-actions-col {
    width: 280px;
    min-width: 280px;
}
.cm-btn {
    font-weight: 700;
    letter-spacing: 0.2px;
    border-radius: 10px;
}
.cm-btn:hover {
    transform: translateY(-1px);
}
.cm-tight .q-field__control {
    min-height: 36px !important;
}
.cm-table {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--input-border);
}
.cm-table .q-table thead tr {
    background: color-mix(in srgb, var(--surface-muted) 84%, var(--primary) 16%);
}
.cm-table .q-table th,
.cm-table .q-table td {
    padding: 4px 8px !important;
}
.cm-table .q-table__middle {
    max-height: 100%;
    overflow: auto;
}
.cm-table .q-table__bottom {
    min-height: 30px;
    padding: 2px 8px;
    font-size: 12px;
}
.cm-half-card {
    display: flex;
    flex-direction: column;
    min-height: 0;
}
.cm-half-body {
    flex: 1;
    min-height: 0;
}
@media (max-width: 1200px) {
    .cm-actions-col {
        width: 240px;
        min-width: 240px;
    }
}
@media (max-width: 980px) {
    .cm-actions-col {
        width: 100%;
        min-width: 0;
    }
    .cm-table .q-table__middle {
        max-height: 96px;
    }
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

    def _publish_cmd(cmd: UiActionName | str) -> None:
        publish_standard_view_action(
            worker_bus=worker_bus,
            view=CONTAINER_MGMT_VIEW,
            cmd_key=CONTAINER_MGMT_CMD_KEY,
            name=cmd,
            event=UiEvent.CLICK,
            wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
            open_wait=wait_dialog["open"],
            source_id=CONTAINER_MGMT_VIEW.value,
        )

    def _publish_cmd_payload(cmd: UiActionName | str, **extra: Any) -> None:
        publish_standard_view_action(
            worker_bus=worker_bus,
            view=CONTAINER_MGMT_VIEW,
            cmd_key=CONTAINER_MGMT_CMD_KEY,
            name=cmd,
            event=UiEvent.CLICK,
            wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
            open_wait=wait_dialog["open"],
            extra=extra,
            source_id=CONTAINER_MGMT_VIEW.value,
        )

    def _label(key: str, fallback: str) -> str:
        return str(t(key, fallback) or fallback).lstrip("@").strip()

    selected_container_tpl = t("container_management.selected_container", "Selected container: {value}")
    selected_serial_tpl = t("container_management.selected_serial", "Selected serial: {value}")

    def _fmt_selected_container(value: Any) -> str:
        v = str(value or "-")
        return (
            selected_container_tpl.replace("{value}", v)
            if "{value}" in selected_container_tpl else f"{selected_container_tpl} {v}"
        )

    def _fmt_selected_serial(value: Any) -> str:
        v = str(value or "-")
        return selected_serial_tpl.replace("{value}", v) if "{value}" in selected_serial_tpl else f"{selected_serial_tpl} {v}"

    def _refresh_tables() -> None:
        table_containers.rows = list(getattr(ctx.state, "container_mgmt_container_rows", []) or [])
        table_serials.rows = list(getattr(ctx.state, "container_mgmt_serial_rows", []) or [])

        selected_bin = str(selected_container.get("value", "") or "")
        if selected_bin:
            selected_rows = [row for row in table_containers.rows if str(row.get("material_bin", "")) == selected_bin]
            table_containers.selected = selected_rows[:1]
        else:
            table_containers.selected = []

        selected_sn = str(selected_serial.get("value", "") or "")
        if selected_sn:
            selected_serial_rows = [row for row in table_serials.rows if str(row.get("serial_number", "")) == selected_sn]
            table_serials.selected = selected_serial_rows[:1]
        else:
            table_serials.selected = []

        table_containers.update()
        table_serials.update()

    def _extract_clicked_row(args: Any, required_key: str) -> dict[str, Any] | None:
        """QTable rowClick payload is typically [mouse_event, row, row_index]."""
        try:
            if isinstance(args, dict):
                row = args.get("row") if isinstance(args.get("row"), dict) else args
                return row if required_key in row else None
            if isinstance(args, (list, tuple)):
                if len(args) > 1 and isinstance(args[1], dict) and required_key in args[1]:
                    return args[1]
                for item in args:
                    if isinstance(item, dict) and required_key in item:
                        return item
            return None
        except Exception:
            return None

    selected_serial: dict[str, str] = {"value": ""}
    selected_container: dict[str, str] = {
        "value": str(getattr(ctx.state, "container_mgmt_container_selected", "") or "")
    }
    selected_container_labels: list[ui.label] = []

    def _set_selected_container(value: str) -> None:
        v = str(value or "")
        selected_container["value"] = v
        setattr(ctx.state, "container_mgmt_container_selected", v)
        text = _fmt_selected_container(v or "-")
        for lbl in selected_container_labels:
            lbl.set_text(text)

    with ui.column().classes("cm-shell w-full h-full min-h-0 overflow-y-auto overflow-x-hidden p-2 gap-2"):
        with ui.row().classes("w-full items-center gap-2 cm-card px-2 py-1"):
            ui.icon("inventory_2").classes("text-lg text-amber-500")
            with ui.column().classes("gap-0"):
                ui.label(t("container_management.title", "Container Management")).classes("text-base font-bold")
                ui.label(t("container_management.subtitle", "Search, activate, and maintain container serials")).classes("text-[10px] text-gray-500")
            ui.space()
            with ui.row().classes("items-center gap-2 cm-chip px-2 py-1"):
                ui.icon("inventory").classes("text-primary text-xs")
                ui.label(t("container_management.active_container", "Active Container:")).classes("text-[11px] text-gray-500")
                ui.label("").classes("text-sm font-bold") \
                    .bind_text_from(ctx.state, "container_mgmt_active_container", backward=lambda n: str(n or "-"))

        with ui.column().classes("w-full flex-1 min-h-0 gap-2"):
            with ui.card().classes("cm-card cm-half-card p-2 w-full flex-1"):
                with ui.row().classes("w-full items-center mb-1"):
                    ui.label(t("container_management.container_results", "Container Results")).classes("cm-title")
                    ui.space()
                    ui.icon("table_view").classes("text-primary text-sm")

                ui.input(t("common.search", "Search Container / Serialnumber")).classes("w-full app-input cm-tight mb-2") \
                    .bind_value(ctx.state, "container_mgmt_search_query")

                with ui.row().classes("cm-half-body w-full gap-2 items-start"):
                    with ui.column().classes("flex-1 min-w-0 h-full min-h-0"):
                        container_columns = [
                            {"name": "material_bin", "label": "MATERIAL_BIN", "field": "material_bin", "align": "left", "sortable": True},
                            {"name": "part_number", "label": "Partnumber", "field": "part_number", "align": "left", "sortable": True},
                            {"name": "current_qty", "label": "Current Qty", "field": "current_qty", "align": "center", "sortable": True},
                        ]
                        table_containers = ui.table(
                            columns=container_columns,
                            rows=[],
                            row_key="material_bin",
                            selection="single",
                            pagination={"rowsPerPage": 50},
                        ).classes("cm-table w-full text-xs")
                        table_containers.props("dense bordered flat separator=horizontal rows-per-page-options=[50,100,200] hide-selected-banner")

                    with ui.column().classes("cm-actions-col gap-2"):
                        selected_container_label_top = ui.label(_fmt_selected_container(selected_container["value"] or "-")).classes("text-xs text-gray-600")
                        selected_container_labels.append(selected_container_label_top)
                        ui.button(
                            _label("container_management.search_by_container", "Search by container"),
                            on_click=lambda: _publish_cmd(UiActionName.SEARCH_CONTAINER),
                            icon="inventory",
                        ).props("color=primary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui.button(
                            _label("container_management.search_by_serial", "Search by Serialnumber"),
                            on_click=lambda: _publish_cmd(UiActionName.SEARCH_SERIAL),
                            icon="qr_code_scanner",
                        ).props("color=secondary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui.button(
                            _label("container_management.activate", "Activate"),
                            on_click=lambda: _publish_cmd(UiActionName.ACTIVATE),
                            icon="bolt",
                        ).props("color=positive text-color=white").classes("w-full h-[36px] cm-btn text-white")

            with ui.card().classes("cm-card cm-half-card p-2 w-full flex-1"):
                with ui.row().classes("w-full items-center mb-1"):
                    ui.label(t("container_management.serials", "Container Serials")).classes("cm-title")
                    ui.space()
                    ui.icon("numbers").classes("text-primary text-sm")

                with ui.row().classes("cm-half-body w-full gap-2 items-start"):
                    with ui.column().classes("flex-1 min-w-0 h-full min-h-0"):
                        serial_columns = [
                            {"name": "serial_number", "label": "Serialnumber", "field": "serial_number", "align": "left", "sortable": True},
                            {"name": "created_on", "label": "Created on", "field": "created_on", "align": "left", "sortable": True},
                        ]
                        table_serials = ui.table(
                            columns=serial_columns,
                            rows=[],
                            row_key="serial_number",
                            selection="single",
                            pagination={"rowsPerPage": 50},
                        ).classes("cm-table w-full text-xs")
                        table_serials.props("dense bordered flat separator=horizontal rows-per-page-options=[50,100,200] hide-selected-banner")

                    with ui.column().classes("cm-actions-col gap-2"):
                        selected_container_label_bottom = ui.label(_fmt_selected_container(selected_container["value"] or "-")).classes("text-xs text-gray-600")
                        selected_container_labels.append(selected_container_label_bottom)
                        ui.button(t("common.search", "Search"), on_click=lambda: _publish_cmd(UiActionName.SEARCH), icon="search") \
                            .props("color=primary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui.button(t("common.refresh", "Refresh"), on_click=lambda: _publish_cmd(UiActionName.REFRESH), icon="refresh") \
                            .props("color=secondary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui.button(
                            _label("container_management.remove_serial", "Remove Serial"),
                            on_click=lambda: _publish_cmd_payload(UiActionName.REMOVE_SERIAL, serial=selected_serial.get("value", "")),
                            icon="remove_circle",
                        ).props("color=warning text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui.button(
                            _label("container_management.remove_all", "Remove All"),
                            on_click=lambda: _publish_cmd(UiActionName.REMOVE_ALL),
                            icon="delete_forever",
                        ).props("color=negative text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        selected_serial_label = ui.label(_fmt_selected_serial("-")).classes("text-xs text-gray-500")

            def _on_container_row_click(e: Any) -> None:
                row = _extract_clicked_row(getattr(e, "args", None), "material_bin")
                if row is None:
                    return
                selected_bin = str(row.get("material_bin", "") or "")
                if selected_bin:
                    _set_selected_container(selected_bin)
                    table_containers.selected = [row]
                    table_containers.update()

            def _on_container_select(e: Any) -> None:
                selection = list(getattr(e, "selection", []) or [])
                if not selection:
                    _set_selected_container("")
                    return
                selected_bin = str(selection[0].get("material_bin", "") or "")
                _set_selected_container(selected_bin)

            table_containers.on("rowClick", _on_container_row_click)
            table_containers.on_select(_on_container_select)

            def _on_serial_click(e: Any) -> None:
                row = _extract_clicked_row(getattr(e, "args", None), "serial_number")
                if row is None:
                    return
                selected_serial["value"] = str(row.get("serial_number", "") or "")
                selected_serial_label.set_text(_fmt_selected_serial(selected_serial["value"]))
                table_serials.selected = [row]
                table_serials.update()

            def _on_serial_select(e: Any) -> None:
                selection = list(getattr(e, "selection", []) or [])
                if not selection:
                    selected_serial["value"] = ""
                    selected_serial_label.set_text(_fmt_selected_serial("-"))
                    return
                selected_serial["value"] = str(selection[0].get("serial_number", "") or "")
                selected_serial_label.set_text(_fmt_selected_serial(selected_serial["value"]))

            table_serials.on("rowClick", _on_serial_click)
            table_serials.on_select(_on_serial_select)

    add_timer(0.2, _refresh_tables)
