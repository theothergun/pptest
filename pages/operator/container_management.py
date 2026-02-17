from __future__ import annotations

import time
from typing import Any

from nicegui import ui
from layout.context import PageContext
from services.i18n import t
from services.worker_topics import WorkerTopics
from loguru import logger


CONTAINER_MGMT_CMD_KEY = "container_management.cmd"


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	worker_bus = ctx.workers.worker_bus

	def _publish_cmd(cmd: str) -> None:
		payload = {
			"cmd": str(cmd),
			"event_id": int(time.time_ns()),
		}
		publish_fn = getattr(worker_bus, "publish", None)
		if not callable(publish_fn):
			logger.warning("Container Management UI command publish skipped: worker_bus.publish is not callable")
			return
		publish_fn(
			topic=WorkerTopics.VALUE_CHANGED,
			source="ui",
			source_id="container_management",
			key=CONTAINER_MGMT_CMD_KEY,
			value=payload,
		)

	def _publish_cmd_payload(cmd: str, **extra: Any) -> None:
		publish_fn = getattr(worker_bus, "publish", None)
		if not callable(publish_fn):
			logger.warning("Container Management UI command publish skipped: worker_bus.publish is not callable")
			return
		payload = {"cmd": str(cmd), "event_id": int(time.time_ns())}
		payload.update({k: v for k, v in extra.items()})
		publish_fn(
			topic=WorkerTopics.VALUE_CHANGED,
			source="ui",
			source_id="container_management",
			key=CONTAINER_MGMT_CMD_KEY,
			value=payload,
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

	ui.timer(0.2, _refresh_tables)
