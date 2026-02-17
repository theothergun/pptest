from __future__ import annotations

import time

from nicegui import ui
from layout.context import PageContext
from services.i18n import t
from services.worker_topics import WorkerTopics
from loguru import logger


PACKAGING_CMD_KEY = "packaging.cmd"


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	worker_bus = ctx.workers.worker_bus

	def _publish_cmd(cmd: str) -> None:
		publish_fn = getattr(worker_bus, "publish", None)
		if not callable(publish_fn):
			logger.warning("Packaging UI command publish skipped: worker_bus.publish is not callable")
			return
		payload = {
			"cmd": str(cmd),
			"event_id": int(time.time_ns()),
		}
		publish_fn(
			topic=WorkerTopics.VALUE_CHANGED,
			source="ui",
			source_id="packaging",
			key=PACKAGING_CMD_KEY,
			value=payload,
		)

	def _input_box_width() -> str:
		return "w-[360px]"

	with ui.column().classes("w-full h-full flex flex-col min-h-0 p-4 gap-4"):
		with ui.row().classes("w-full items-center gap-4"):
			ui.label(t("packaging.title", "Packaging")).classes("text-2xl font-bold")
			ui.space()

		with ui.card().classes("w-full max-w-[720px] p-4"):
			with ui.column().classes("w-full gap-3"):
				with ui.row().classes("w-full items-center gap-4"):
					ui.label(t("packaging.container_number", "Container")).classes("w-[180px] text-sm app-muted")
					ui.input().props("readonly").classes(_input_box_width()).bind_value_from(
						ctx.state, "container_number", backward=lambda n: str(n or "")
					)

				with ui.row().classes("w-full items-center gap-4"):
					ui.label(t("packaging.part_number", "@Partnumber")).classes("w-[180px] text-sm app-muted")
					ui.input().props("readonly").classes(_input_box_width()).bind_value_from(
						ctx.state, "part_number", backward=lambda n: str(n or "")
					)

				with ui.row().classes("w-full items-center gap-4"):
					ui.label(t("packaging.description", "PartDescription")).classes("w-[180px] text-sm app-muted")
					ui.input().props("readonly").classes(_input_box_width()).bind_value_from(
						ctx.state, "description", backward=lambda n: str(n or "-")
					)

				with ui.row().classes("w-full items-center gap-4"):
					ui.label(t("packaging.quantity", "Quantity")).classes("w-[180px] text-sm app-muted")
					with ui.row().classes("items-center gap-2"):
						ui.input().props("readonly").classes("w-[150px] text-center") \
							.bind_value_from(ctx.state, "current_container_qty", backward=lambda n: str(n or "0"))
						ui.label("/").classes("text-base app-muted")
						ui.input().props("readonly").classes("w-[150px] text-center") \
							.bind_value_from(ctx.state, "max_container_qty", backward=lambda n: str(n or "0"))

				with ui.row().classes("w-full items-center gap-4"):
					ui.label(t("packaging.last_serial_number", "Last Serialnumber")).classes("w-[180px] text-sm app-muted")
					ui.input().props("readonly").classes(_input_box_width()).bind_value_from(
						ctx.state, "last_serial_number", backward=lambda n: str(n or "")
					)

		with ui.row().classes("w-full max-w-[720px] gap-4 justify-start"):
			ui.button(t("common.remove", "Remove"), icon="delete", on_click=lambda: _publish_cmd("remove")) \
				.props("outline").classes("w-[140px]")
			ui.button(t("common.print", "Print"), icon="print", on_click=lambda: _publish_cmd("print")) \
				.props("outline").classes("w-[140px]")
			ui.button(t("common.new", "New"), icon="add", on_click=lambda: _publish_cmd("new")) \
				.props("outline").classes("w-[140px]")
			ui.button(t("common.refresh", "Refresh"), icon="refresh", on_click=lambda: _publish_cmd("refresh")) \
				.props("outline").classes("w-[140px]")
