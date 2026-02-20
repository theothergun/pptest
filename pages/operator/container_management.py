from __future__ import annotations

from typing import Any

from nicegui import ui
from layout.context import PageContext
from services.i18n import t
from services.ui.view_cmd import install_wait_dialog, publish_view_cmd, view_wait_key


CONTAINER_MGMT_CMD_KEY = "container_management.cmd"
CONTAINER_MGMT_VIEW = "container_management"
CONTAINER_MGMT_WAIT_MODAL_KEY = view_wait_key(CONTAINER_MGMT_VIEW)


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	worker_bus = ctx.workers.worker_bus
	page_timers: list = []

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		for sub in wait_dialog["subs"]:
			try:
				sub.close()
			except Exception:
				pass
		for t in page_timers:
			try:
				t.cancel()
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
		publish_view_cmd(
			worker_bus=worker_bus,
			view=CONTAINER_MGMT_VIEW,
			cmd_key=CONTAINER_MGMT_CMD_KEY,
			cmd=cmd,
			wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
			open_wait=wait_dialog["open"],
			source_id=CONTAINER_MGMT_VIEW,
		)

	def _publish_cmd_payload(cmd: str, **extra: Any) -> None:
		publish_view_cmd(
			worker_bus=worker_bus,
			view=CONTAINER_MGMT_VIEW,
			cmd_key=CONTAINER_MGMT_CMD_KEY,
			cmd=cmd,
			wait_key=CONTAINER_MGMT_WAIT_MODAL_KEY,
			open_wait=wait_dialog["open"],
			extra=extra,
			source_id=CONTAINER_MGMT_VIEW,
		)

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

	with ui.column().classes("w-full h-full flex flex-col min-h-0 p-4 gap-4"):
		with ui.column().classes("w-full gap-2"):
			with ui.element("div").classes("w-full bg-primary text-white font-semibold px-3 py-2"):
				ui.label(t("container_management.search_container", "Search Container")).classes("text-white")

		with ui.row().classes("w-full items-start gap-4"):
			with ui.column().classes("flex-1 gap-2"):
				ui.input().classes("w-full app-input") \
					.bind_value_from(ctx.state, "container_mgmt_search_query", backward=lambda n: str(n or ""))

				columns = [
					{"name": "material_bin", "label": "MATERIAL_BIN", "field": "material_bin", "align": "left"},
					{"name": "part_number", "label": "Partnumber", "field": "part_number", "align": "left"},
					{"name": "current_qty", "label": "Current Qty", "field": "current_qty", "align": "center"},
				]
				table_containers = ui.table(columns=columns, rows=[], row_key="material_bin") \
					.classes("w-full text-sm") \
					.props("dense separator=cell")

			with ui.column().classes("w-[210px] gap-3"):
					ui.button(t("container_management.search_by_container", "@Search by container"),
							  on_click=lambda: _publish_cmd("search_container")) \
						.props("outline").classes("w-full")
					ui.button(t("container_management.search_by_serial", "@Search by Serialnumber"),
							  on_click=lambda: _publish_cmd("search_serial")) \
						.props("outline").classes("w-full")
					ui.button(t("container_management.activate", "@Activate"),
							  on_click=lambda: _publish_cmd("activate")) \
						.props("outline").classes("w-full")


		with ui.element("div").classes("w-full bg-primary text-white font-semibold px-3 py-2"):
			ui.label("").classes("text-white").bind_text_from(
				ctx.state,
				"container_mgmt_active_container",
				backward=lambda n: "Packaging Container - %s" % (str(n or "-")),
			)

		with ui.row().classes("w-full items-start gap-4"):
			with ui.column().classes("flex-1 gap-2"):
				ui.input().classes("w-full app-input") \
					.bind_value_from(ctx.state, "container_mgmt_container_selected", backward=lambda n: str(n or ""))

				serial_columns = [
					{"name": "serial_number", "label": "@Serialnumber", "field": "serial_number", "align": "left"},
					{"name": "created_on", "label": "Created on", "field": "created_on", "align": "left"},
				]
				table_serials = ui.table(columns=serial_columns, rows=[], row_key="serial_number") \
					.classes("w-full text-sm") \
					.props("dense separator=cell")
				def _on_serial_click(e: Any) -> None:
					row = _extract_clicked_row(getattr(e, "args", None))
					if row is None:
						return
					selected_serial["value"] = str(row.get("serial_number", "") or "")

				table_serials.on("rowClick", _on_serial_click)

			with ui.column().classes("w-[210px] gap-3"):
				ui.button(t("common.search", "Search"), on_click=lambda: _publish_cmd("search")) \
					.props("outline").classes("w-full")
				ui.button(t("common.refresh", "Refresh"), on_click=lambda: _publish_cmd("refresh")) \
					.props("outline").classes("w-full")
				ui.button(t("container_management.remove_serial", "Remove Serial"),
						  on_click=lambda: _publish_cmd_payload("remove_serial", serial=selected_serial.get("value", ""))) \
					.props("outline").classes("w-full")
				ui.button(t("container_management.remove_all", "Remove All"),
						  on_click=lambda: _publish_cmd("remove_all")) \
					.props("outline").classes("w-full")

	add_timer(0.2, _refresh_tables)
