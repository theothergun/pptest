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
    ui_refs: dict[str, Any] = {
        "btn_search_container": None,
        "btn_search_serial": None,
        "btn_activate": None,
        "btn_search": None,
        "btn_refresh": None,
        "btn_remove_serial": None,
        "btn_remove_all": None,
    }

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
.cm-btn.q-btn--disabled,
.cm-btn.q-btn--disabled:hover,
.cm-btn.q-btn--disabled.q-btn--outline {
    background-color: #9ca3af !important;
    border-color: #6b7280 !important;
    color: #374151 !important;
    opacity: 1 !important;
    transform: none !important;
    box-shadow: none !important;
    filter: grayscale(1) saturate(0.2) !important;
}
.cm-btn.q-btn--disabled .q-btn__content,
.cm-btn.q-btn--disabled .q-icon,
.cm-btn.q-btn--disabled .block {
    color: #374151 !important;
}
.cm-btn.q-btn--disabled .q-focus-helper {
    opacity: 0 !important;
}
.cm-btn-force-disabled {
    background: #9ca3af !important;
    border-color: #6b7280 !important;
    color: #374151 !important;
    opacity: 1 !important;
    box-shadow: none !important;
}
.cm-btn-force-disabled .q-btn__content,
.cm-btn-force-disabled .q-icon,
.cm-btn-force-disabled .block {
    color: #374151 !important;
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
.cm-table .q-table__middle thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: color-mix(in srgb, var(--surface-muted) 84%, var(--primary) 16%);
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

    serial_filter: dict[str, str] = {"value": ""}

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

    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            raw = str(value).strip().replace(",", ".")
            if not raw:
                return None
            return float(raw)
        except Exception:
            return None

    def _fmt_num(value: float | None) -> str:
        if value is None:
            return "-"
        if abs(value - int(value)) < 1e-9:
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def _enrich_container_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            entry = dict(row)
            raw_qty = entry.get("current_qty")
            current = None
            max_qty = None

            if isinstance(raw_qty, dict):
                current = _to_float(raw_qty.get("current"))
                if current is None:
                    current = _to_float(raw_qty.get("value"))
                max_qty = _to_float(raw_qty.get("max"))
            elif isinstance(raw_qty, (list, tuple)) and len(raw_qty) >= 2:
                current = _to_float(raw_qty[0])
                max_qty = _to_float(raw_qty[1])
            else:
                raw_txt = str(raw_qty or "").strip()
                if "/" in raw_txt:
                    parts = raw_txt.split("/", 1)
                    current = _to_float(parts[0])
                    max_qty = _to_float(parts[1])

            if current is None:
                current = _to_float(entry.get("current"))
            if current is None:
                current = _to_float(entry.get("current_qty_value"))

            if max_qty is None:
                max_qty = _to_float(entry.get("max"))
            if max_qty is None:
                max_qty = _to_float(entry.get("max_qty"))
            if max_qty is None:
                max_qty = _to_float(entry.get("max_container_qty"))

            progress = 0.0
            if max_qty and max_qty > 0 and current is not None:
                progress = current / max_qty
            progress = max(0.0, min(1.0, float(progress)))

            label = str(raw_qty or "").strip() or "-"
            if current is not None and max_qty is not None:
                label = f"{_fmt_num(current)}/{_fmt_num(max_qty)}"

            entry["current_qty_current"] = current
            entry["current_qty_max"] = max_qty
            entry["current_qty_progress"] = progress
            entry["current_qty_label"] = label
            out.append(entry)
        return out

    def _refresh_tables() -> None:
        raw_container_rows = list(getattr(ctx.state, "container_mgmt_container_rows", []) or [])
        table_containers.rows = _enrich_container_rows(raw_container_rows)
        serial_rows = list(getattr(ctx.state, "container_mgmt_serial_rows", []) or [])
        filter_value = str(serial_filter.get("value", "") or "").strip().lower()
        if filter_value:
            serial_rows = [
                row for row in serial_rows
                if filter_value in str(row.get("serial_number", "") or "").lower()
            ]
        table_serials.rows = serial_rows

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

    def _button_enabled(button_id: str) -> bool:
        states = getattr(ctx.state, "view_button_states", {}) or {}
        if not isinstance(states, dict):
            return True
        local_key = f"{CONTAINER_MGMT_VIEW.value}.{button_id}"
        if local_key in states:
            return bool(states.get(local_key))
        if button_id in states:
            return bool(states.get(button_id))
        return True

    def _button_visible(button_id: str) -> bool:
        vis = getattr(ctx.state, "view_button_visibility", {}) or {}
        if not isinstance(vis, dict):
            return True
        local_key = f"{CONTAINER_MGMT_VIEW.value}.{button_id}"
        if local_key in vis:
            return bool(vis.get(local_key))
        if button_id in vis:
            return bool(vis.get(button_id))
        return True

    def _apply_button_states() -> None:
        for button_id, ref_key in (
            ("search_container", "btn_search_container"),
            ("search_serial", "btn_search_serial"),
            ("activate", "btn_activate"),
            ("search", "btn_search"),
            ("refresh", "btn_refresh"),
            ("remove_serial", "btn_remove_serial"),
            ("remove_all", "btn_remove_all"),
        ):
            btn = ui_refs.get(ref_key)
            if btn is None:
                continue
            enabled = _button_enabled(button_id)
            # Keep REMOVE_SERIAL tied to current container selection immediately on UI side.
            if button_id == "remove_serial":
                enabled = bool(str(getattr(ctx.state, "container_mgmt_container_selected", "") or "").strip())
            try:
                btn.visible = _button_visible(button_id)
                if enabled:
                    btn.enable()
                    btn.classes(remove="cm-btn-force-disabled")
                else:
                    btn.disable()
                    btn.classes(add="cm-btn-force-disabled")
            except Exception:
                pass

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
        ctx.set_state_and_publish("container_mgmt_container_selected", v)
        text = _fmt_selected_container(v or "-")
        for lbl in selected_container_labels:
            lbl.set_text(text)
        _apply_button_states()

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

                search_input = ui.input(t("common.search", "Search Container / Serialnumber")).classes("w-full app-input cm-tight mb-2")
                search_input.bind_value(ctx.state, "container_mgmt_search_query")
                search_input.on_value_change(
                    lambda e: ctx.set_state_and_publish(
                        "container_mgmt_search_query",
                        str(getattr(e, "value", "") or ""),
                    )
                )

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
                        table_containers.add_slot(
                            "body-cell-current_qty",
                            """
<q-td :props="props">
  <div class="w-full" style="min-width: 120px;">
    <div class="text-[11px] text-gray-600" style="line-height: 1.1;">
      {{ props.row.current_qty_label || '-' }}
    </div>
    <q-linear-progress
      size="8px"
      rounded
      :value="props.row.current_qty_progress || 0"
      color="primary"
      track-color="grey-3"
      class="q-mt-xs"
    />
  </div>
</q-td>
""",
                        )

                    with ui.column().classes("cm-actions-col gap-2"):
                        selected_container_label_top = ui.label(_fmt_selected_container(selected_container["value"] or "-")).classes("text-xs text-gray-600")
                        selected_container_labels.append(selected_container_label_top)
                        ui_refs["btn_search_container"] = ui.button(
                            _label("container_management.search_by_container", "Search by container"),
                            on_click=lambda: _publish_cmd(UiActionName.SEARCH_CONTAINER),
                            icon="inventory",
                        ).props("color=primary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui_refs["btn_search_serial"] = ui.button(
                            _label("container_management.search_by_serial", "Search by Serialnumber"),
                            on_click=lambda: _publish_cmd(UiActionName.SEARCH_SERIAL),
                            icon="qr_code_scanner",
                        ).props("color=secondary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui_refs["btn_activate"] = ui.button(
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
                        serial_filter_input = ui.input(
                            t("container_management.filter_serials", "Filter serials")
                        ).classes("w-full app-input cm-tight")
                        serial_filter_input.on_value_change(
                            lambda e: (
                                serial_filter.__setitem__("value", str(getattr(e, "value", "") or "")),
                                _refresh_tables(),
                            )
                        )
                        selected_container_label_bottom = ui.label(_fmt_selected_container(selected_container["value"] or "-")).classes("text-xs text-gray-600")
                        selected_container_labels.append(selected_container_label_bottom)
                        ui_refs["btn_search"] = ui.button(t("common.search", "Search"), on_click=lambda: _publish_cmd(UiActionName.SEARCH), icon="search") \
                            .props("color=primary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui_refs["btn_refresh"] = ui.button(t("common.refresh", "Refresh"), on_click=lambda: _publish_cmd(UiActionName.REFRESH), icon="refresh") \
                            .props("color=secondary text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui_refs["btn_remove_serial"] = ui.button(
                            _label("container_management.remove_serial", "Remove Serial"),
                            on_click=lambda: _publish_cmd_payload(UiActionName.REMOVE_SERIAL, serial=selected_serial.get("value", "")),
                            icon="remove_circle",
                        ).props("color=warning text-color=white").classes("w-full h-[36px] cm-btn text-white")
                        ui_refs["btn_remove_all"] = ui.button(
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
                ctx.set_state_and_publish("container_mgmt_serial_selected", selected_serial["value"])
                selected_serial_label.set_text(_fmt_selected_serial(selected_serial["value"]))
                table_serials.selected = [row]
                table_serials.update()

            def _on_serial_select(e: Any) -> None:
                selection = list(getattr(e, "selection", []) or [])
                if not selection:
                    selected_serial["value"] = ""
                    ctx.set_state_and_publish("container_mgmt_serial_selected", "")
                    selected_serial_label.set_text(_fmt_selected_serial("-"))
                    return
                selected_serial["value"] = str(selection[0].get("serial_number", "") or "")
                ctx.set_state_and_publish("container_mgmt_serial_selected", selected_serial["value"])
                selected_serial_label.set_text(_fmt_selected_serial(selected_serial["value"]))

            table_serials.on("rowClick", _on_serial_click)
            table_serials.on_select(_on_serial_select)

    add_timer(0.2, _refresh_tables)
    add_timer(0.2, _apply_button_states)
