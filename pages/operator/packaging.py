from __future__ import annotations

import queue
import time
from typing import Any

from nicegui import ui
from layout.context import PageContext
from services.i18n import t
from services.app_config import get_app_config
from services.ui_theme import get_theme_color
from services.worker_topics import WorkerTopics
from loguru import logger


PACKAGING_CMD_KEY = "packaging.cmd"


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	cfg = get_app_config()
	worker_bus = ctx.workers.worker_bus
	bridge = ctx.bridge

	# --- lifecycle management (same pattern as your Scripts Lab page) ---
	page_timers: list = []
	sub_state = bridge.subscribe_many([
		"state.container_number",
		"state.part_number",
		"state.description",
		"state.work_instruction",
		"state.work_instruction_state",
		"state.work_feedback",
		"state.work_feedback_state",
		"state.current_container_qty",
		"state.max_container_qty",
		"state.part_good",
		"state.part_bad",
	])

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		try:
			sub_state.close()
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
	# -------------------------------------------------------------------

	# --------------------------
	# UI refs (only for styling)
	# --------------------------
	ui_refs: dict[str, Any] = {
		"card_current_qty": None,
		"card_max_qty": None,

		"card_instruction": None,  # NEW
		"card_feedback": None,  # NEW
	}

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

	def _set_counter_cards_color(current_qty: int, max_qty: int) -> None:
		# rules:
		# - red if both 0
		# - orange if 0 < current < max (or max == 0 but current > 0)
		# - green if max > 0 and current >= max
		if current_qty == 0 and max_qty == 0:
			bg = get_theme_color(cfg, "status-bad", "#FCA5A5")
		elif max_qty > 0 and current_qty >= max_qty:
			bg = get_theme_color(cfg, "status-good", "#86EFAC")
		else:
			bg = get_theme_color(cfg, "status-warning", "#FDBA74")

		card_a = ui_refs.get("card_current_qty")
		card_b = ui_refs.get("card_max_qty")
		if card_a is not None:
			try:
				card_a.style("background-color: %s;" % bg)
			except Exception:
				pass
		if card_b is not None:
			try:
				card_b.style("background-color: %s;" % bg)
			except Exception:
				pass

	# ---------------------------------------------------------
	# NEW: instruction/feedback state -> background color logic
	# ---------------------------------------------------------
	def _bg_for_state(state: int) -> str:
		# 1=Green, 2=Yellow, 3=Red, 4=Blue, 5=Grey
		if state == 1:
			return get_theme_color(cfg, "status-good", "#86EFAC")
		if state == 2:
			return get_theme_color(cfg, "status-warning", "#FDE68A")
		if state == 3:
			return get_theme_color(cfg, "status-bad", "#FCA5A5")
		if state == 4:
			return get_theme_color(cfg, "status-info", "#93C5FD")
		return get_theme_color(cfg, "status-muted", "#E5E7EB")

	def _set_instruction_feedback_cards_color(work_instruction_state: int, work_feedback_state: int) -> None:
		card_instruction = ui_refs.get("card_instruction")
		card_feedback = ui_refs.get("card_feedback")

		bg_instruction = _bg_for_state(work_instruction_state)
		bg_feedback = _bg_for_state(work_feedback_state)

		if card_instruction is not None:
			try:
				card_instruction.style("background-color: %s;" % bg_instruction)
			except Exception:
				pass

		if card_feedback is not None:
			try:
				card_feedback.style("background-color: %s;" % bg_feedback)
			except Exception:
				pass

	# --------------------------
	# Layout
	# --------------------------
	with ui.column().classes("w-full h-full flex flex-col min-h-0 p-4 gap-4"):
		with ui.row().classes("w-full items-center gap-4"):
			ui.label(t("packaging.title", "📦 packaging Station")).classes("text-2xl font-bold")
			ui.space()

		with ui.grid().classes("w-full gap-4").style("grid-template-columns: 360px 1fr 280px;"):
			with ui.card().classes("w-full"):
				ui.label(t("packaging.container_number", "Containernumber")).classes("text-sm text-gray-500")
				ui.label("").classes("text-lg font-bold") \
					.bind_text_from(ctx.state, "container_number", backward=lambda n: str(n or ""))

				ui.separator()

				ui.label(t("packaging.part_number", "Partnumber")).classes("text-sm text-gray-500")
				ui.label("").classes("text-lg font-bold") \
					.bind_text_from(ctx.state, "part_number", backward=lambda n: str(n or ""))

				ui.separator()

				ui.label(t("common.description", "Description")).classes("text-sm text-gray-500")
				ui.label("").classes("text-base") \
					.bind_text_from(ctx.state, "description", backward=lambda n: str(n or ""))

				ui.separator()

				with ui.row().classes("w-full justify-between items-center mt-2"):
					ui_refs["card_current_qty"] = ui.card().classes("w-[140px] h-[80px] flex items-center justify-center")
					with ui_refs["card_current_qty"]:
						ui.label("").classes("text-3xl font-bold") \
							.bind_text_from(ctx.state, "current_container_qty", backward=lambda n: "%s" % int(n or 0))
						ui.label(t("common.current", "Current")).classes("text-xs text-gray-700")

					ui_refs["card_max_qty"] = ui.card().classes("w-[140px] h-[80px] flex items-center justify-center")
					with ui_refs["card_max_qty"]:
						ui.label("").classes("text-3xl font-bold") \
							.bind_text_from(ctx.state, "max_container_qty", backward=lambda n: "%s" % int(n or 0))
						ui.label(t("common.max", "Max")).classes("text-xs text-gray-700")

			with ui.column().classes("w-full gap-4"):
				ui_refs["card_instruction"] = ui.card().classes("w-full")  # NEW ref
				with ui_refs["card_instruction"]:
					ui.label(t("packaging.instruction_for_worker", "Instruction for worker")).classes("text-sm text-gray-700")
					lbl_instruction = ui.label("").classes("text-xl font-semibold")
					lbl_instruction.style("min-height: 72px;")
					lbl_instruction.bind_text_from(ctx.state, "work_instruction", backward=lambda n: str(n or ""))

				ui_refs["card_feedback"] = ui.card().classes("w-full")  # NEW ref
				with ui_refs["card_feedback"]:
					ui.label(t("packaging.current_step", "Current step")).classes("text-sm text-gray-700")
					lbl_step = ui.label("").classes("text-xl font-semibold")
					lbl_step.style("min-height: 72px;")
					lbl_step.bind_text_from(ctx.state, "work_feedback", backward=lambda n: str(n or ""))

			with ui.card().classes("w-full"):
				ui.label(t("packaging.total_good", "Total good")).classes("text-sm text-gray-500")
				ui.label("").classes("text-4xl font-bold") \
					.bind_text_from(ctx.state, "part_good", backward=lambda n: "%s" % int(n or 0))

				ui.separator()

				ui.label(t("packaging.total_bad", "Total bad")).classes("text-sm text-gray-500")
				ui.label("").classes("text-4xl font-bold") \
					.bind_text_from(ctx.state, "part_bad", backward=lambda n: "%s" % int(n or 0))

		with ui.row().classes("w-full gap-4 justify-start"):
			ui.button(t("common.start", "Start"), icon="play_arrow", on_click=lambda: _publish_cmd("start")) \
				.props("color=positive").classes("w-[200px] h-[64px] text-lg")
			ui.button(t("common.stop", "Stop"), icon="stop", on_click=lambda: _publish_cmd("stop")) \
				.props("color=negative").classes("w-[200px] h-[64px] text-lg")
			ui.button(t("common.reset", "Reset"), icon="restart_alt", on_click=lambda: _publish_cmd("reset")) \
				.props("color=info outline").classes("w-[240px] h-[64px] text-lg")

	# --------------------------
	# Drain bridge for style updates
	# --------------------------
	def _apply_counter_color_from_state() -> None:
		cur_qty = int(getattr(ctx.state, "current_container_qty", 0) or 0)
		max_qty = int(getattr(ctx.state, "max_container_qty", 0) or 0)
		_set_counter_cards_color(cur_qty, max_qty)

	def _apply_instruction_feedback_color_from_state() -> None:
		instr_state = int(getattr(ctx.state, "work_instruction_state", 4) or 4)
		feed_state = int(getattr(ctx.state, "work_feedback_state", 4) or 4)
		_set_instruction_feedback_cards_color(instr_state, feed_state)

	def _drain_bus() -> None:
		changed_counter = False
		changed_text_boxes = False

		while True:
			try:
				msg = sub_state.queue.get_nowait()
			except queue.Empty:
				break

			key = msg.topic.replace("state.", "")
			if key in ("current_container_qty", "max_container_qty"):
				changed_counter = True
			elif key in ("work_instruction_state", "work_feedback_state"):
				changed_text_boxes = True

		if changed_counter:
			_apply_counter_color_from_state()
		if changed_text_boxes:
			_apply_instruction_feedback_color_from_state()

	add_timer(0.1, _drain_bus)
	_apply_counter_color_from_state()
	_apply_instruction_feedback_color_from_state()
