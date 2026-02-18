from __future__ import annotations

import queue
import time
from typing import Any

from nicegui import ui
from layout.context import PageContext
from services.app_config import get_app_config
from services.i18n import t
from services.ui_theme import get_theme_color
from services.worker_topics import WorkerTopics
from loguru import logger


PACKAGING_CMD_KEY = "packaging.cmd"
PACKAGING_WAIT_MODAL_KEY = "packaging.wait"


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		build_page(ctx)


def build_page(ctx: PageContext) -> None:
	cfg = get_app_config()
	worker_bus = ctx.workers.worker_bus
	page_timers: list = []
	sub_wait_close = worker_bus.subscribe(WorkerTopics.TOPIC_MODAL_CLOSE)
	sub_wait_open = worker_bus.subscribe(WorkerTopics.VALUE_CHANGED)
	ui_refs: dict[str, Any] = {
		"card_instruction": None,
		"card_feedback": None,
		"instruction_badge": None,
		"feedback_badge": None,
		"qty_progress": None,
		"qty_ratio": None,
	}

	ui.add_head_html("""
<style>
@keyframes pack-wait-spin {
	from { transform: rotate(0deg); }
	to { transform: rotate(360deg); }
}
.pack-wait-spin {
	animation: pack-wait-spin 1s linear infinite;
}
.pack-shell {
	background: linear-gradient(135deg, var(--surface-muted) 0%, var(--app-background) 100%);
	border-radius: 20px;
}
.pack-card {
	border: 1px solid var(--input-border);
	border-radius: 16px;
	box-shadow: 0 8px 24px rgba(16, 24, 40, 0.06);
	background: var(--surface);
	color: var(--text-primary);
	overflow: hidden;
}
.pack-fade {
	animation: packFadeIn 260ms ease-out;
}
.pack-btn {
	font-weight: 700;
	letter-spacing: 0.2px;
	border-radius: 12px;
	transition: transform 120ms ease, box-shadow 120ms ease;
}
.pack-btn:hover {
	transform: translateY(-1px);
	box-shadow: 0 8px 18px rgba(15, 23, 42, 0.14);
}
.pack-header {
	min-height: 62px;
}
.pack-shell .pack-primary { color: var(--primary) !important; }
.pack-shell .pack-positive { color: var(--positive) !important; }
.pack-shell .pack-negative { color: var(--negative) !important; }
.pack-shell .pack-text-primary { color: var(--text-primary) !important; }
.pack-shell .pack-text-secondary { color: var(--text-secondary) !important; }
@keyframes packFadeIn {
	from { opacity: 0; transform: translateY(6px); }
	to { opacity: 1; transform: translateY(0); }
}
</style>
""")

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		try:
			sub_wait_close.close()
		except Exception:
			pass
		try:
			sub_wait_open.close()
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

	wait_state = {"open": False}
	wait_text_refs: dict[str, Any] = {"title": None, "message": None}
	with ui.dialog().props("persistent") as wait_dialog:
		with ui.card().classes("w-72 items-center gap-3 py-6"):
			ui.icon("hourglass_top").classes("text-primary text-4xl pack-wait-spin")
			wait_text_refs["title"] = ui.label(t("packaging.wait_title", "Please wait")).classes("text-base font-semibold")
			wait_text_refs["message"] = ui.label(t("packaging.working", "Working ...")).classes("text-sm font-medium")

	def _set_wait_dialog_text(title: str | None = None, message: str | None = None) -> None:
		title_ref = wait_text_refs.get("title")
		msg_ref = wait_text_refs.get("message")
		if title_ref is not None and title is not None:
			title_ref.set_text(str(title))
		if msg_ref is not None and message is not None:
			msg_ref.set_text(str(message))

	def _open_wait_dialog() -> None:
		if wait_state["open"]:
			return
		wait_state["open"] = True
		wait_dialog.open()

	def _close_wait_dialog() -> None:
		if not wait_state["open"]:
			return
		wait_state["open"] = False
		wait_dialog.close()

	def _drain_wait_open_signal() -> None:
		while True:
			try:
				msg = sub_wait_open.queue.get_nowait()
			except queue.Empty:
				break
			payload = getattr(msg, "payload", None) or {}
			if not isinstance(payload, dict):
				continue
			key = str(payload.get("key") or "").strip()
			if key != PACKAGING_WAIT_MODAL_KEY:
				continue
			value = payload.get("value")
			if not isinstance(value, dict):
				continue
			action = str(value.get("action") or "").strip().lower()
			if action == "open":
				_set_wait_dialog_text(
					title=str(value.get("title") or t("packaging.wait_title", "Please wait")),
					message=str(value.get("message") or t("packaging.working", "Working ...")),
				)
				_open_wait_dialog()
			elif action == "close":
				_close_wait_dialog()

	def _drain_wait_close_signal() -> None:
		while True:
			try:
				msg = sub_wait_close.queue.get_nowait()
			except queue.Empty:
				break
			payload = getattr(msg, "payload", None) or {}
			if not isinstance(payload, dict):
				continue
			if bool(payload.get("close_active", False)):
				_close_wait_dialog()
				continue
			key = str(payload.get("key") or "").strip()
			if key in (PACKAGING_WAIT_MODAL_KEY, PACKAGING_CMD_KEY):
				_close_wait_dialog()

	def _publish_cmd(cmd: str) -> None:
		publish_fn = getattr(worker_bus, "publish", None)
		if not callable(publish_fn):
			logger.warning("Packaging UI command publish skipped: worker_bus.publish is not callable")
			return
		_open_wait_dialog()
		payload = {
			"cmd": str(cmd),
			"event_id": int(time.time_ns()),
			"wait_modal_key": PACKAGING_WAIT_MODAL_KEY,
		}
		publish_fn(
			topic=WorkerTopics.VALUE_CHANGED,
			source="ui",
			source_id="packaging",
			key=PACKAGING_CMD_KEY,
			value=payload,
		)

	def _input_box_width() -> str:
		return "w-full"

	def _state_visual(state: int) -> tuple[str, str, str]:
		# 1=good, 2=warn, 3=bad, 4=info, 5=idle/default
		if state == 1:
			return get_theme_color(cfg, "status-good", "#86efac"), get_theme_color(cfg, "positive", "#16a34a"), "GOOD"
		if state == 2:
			return get_theme_color(cfg, "status-warning", "#fdba74"), get_theme_color(cfg, "warning", "#f59e0b"), "WARN"
		if state == 3:
			return get_theme_color(cfg, "status-bad", "#fca5a5"), get_theme_color(cfg, "negative", "#dc2626"), "BAD"
		if state == 4:
			return get_theme_color(cfg, "status-info", "#93c5fd"), get_theme_color(cfg, "info", "#0284c7"), "INFO"
		return get_theme_color(cfg, "status-muted", "#e5e7eb"), get_theme_color(cfg, "text-secondary", "#475569"), "IDLE"

	def _apply_instruction_feedback_colors() -> None:
		instr_state = int(getattr(ctx.state, "work_instruction_state", 5) or 5)
		feed_state = int(getattr(ctx.state, "work_feedback_state", 5) or 5)

		card_instruction = ui_refs.get("card_instruction")
		card_feedback = ui_refs.get("card_feedback")
		instruction_badge = ui_refs.get("instruction_badge")
		feedback_badge = ui_refs.get("feedback_badge")

		ibg, iborder, ilabel = _state_visual(instr_state)
		fbg, fborder, flabel = _state_visual(feed_state)

		if card_instruction is not None:
			card_instruction.style(f"background-color: {ibg}; border-left: 6px solid {iborder};")
		if card_feedback is not None:
			card_feedback.style(f"background-color: {fbg}; border-left: 6px solid {fborder};")
		if instruction_badge is not None:
			instruction_badge.set_text(ilabel)
			instruction_badge.style(f"background:{iborder}; color:#fff;")
		if feedback_badge is not None:
			feedback_badge.set_text(flabel)
			feedback_badge.style(f"background:{fborder}; color:#fff;")

	def _apply_qty_progress() -> None:
		cur = int(getattr(ctx.state, "current_container_qty", 0) or 0)
		max_qty = int(getattr(ctx.state, "max_container_qty", 0) or 0)
		ratio = 0.0 if max_qty <= 0 else max(0.0, min(1.0, cur / max_qty))

		qty_progress = ui_refs.get("qty_progress")
		qty_ratio = ui_refs.get("qty_ratio")
		if qty_progress is not None:
			qty_progress.value = ratio
			qty_progress.update()
		if qty_ratio is not None:
			qty_ratio.set_text(f"{int(ratio * 100)}%")

	with ui.column().classes("pack-shell w-full h-full flex flex-col min-h-0 p-4 gap-3"):
		with ui.row().classes("pack-header w-full items-center gap-2 pack-card p-2 pack-fade"):
			ui.icon("inventory_2").classes("text-xl pack-primary")
			with ui.column().classes("gap-0"):
				ui.label(t("packaging.title", "Packaging")).classes("text-lg font-bold pack-text-primary leading-none")
				ui.label(t("packaging.subtitle", "Live production and operator workflow")).classes("text-[11px] pack-text-secondary mt-0.5")
			ui.space()
			with ui.row().classes("items-center gap-2"):
				with ui.card().classes("pack-card p-2 min-w-[96px]"):
					with ui.row().classes("items-center gap-1"):
						ui.icon("check_circle").classes("pack-positive text-sm")
						ui.label(t("packaging.total_good", "Good")).classes("text-xs pack-text-secondary")
					ui.label("").classes("text-base font-black pack-positive leading-none") \
						.bind_text_from(ctx.state, "part_good", backward=lambda n: str(int(n or 0)))
				with ui.card().classes("pack-card p-2 min-w-[88px]"):
					with ui.row().classes("items-center gap-1"):
						ui.icon("cancel").classes("pack-negative text-sm")
						ui.label(t("packaging.total_bad", "Bad")).classes("text-xs pack-text-secondary")
					ui.label("").classes("text-base font-black pack-negative leading-none") \
						.bind_text_from(ctx.state, "part_bad", backward=lambda n: str(int(n or 0)))

		with ui.element("div").classes("w-full grid grid-cols-1 lg:grid-cols-2 gap-4"):
			ui_refs["card_instruction"] = ui.card().classes("pack-card pack-fade p-3 w-full")
			with ui_refs["card_instruction"]:
				with ui.row().classes("items-center w-full"):
					ui.icon("playlist_add_check").classes("text-xl pack-text-primary")
					ui.label(t("packaging.instruction_for_worker", "Instruction")).classes("ml-2 text-sm font-bold pack-text-primary")
					ui.space()
					ui_refs["instruction_badge"] = ui.badge("IDLE").classes("font-bold")
				ui.label("").classes("text-base font-semibold pack-text-primary mt-2 leading-snug") \
					.style("min-height: 56px;") \
					.bind_text_from(ctx.state, "work_instruction", backward=lambda n: str(n or ""))

			ui_refs["card_feedback"] = ui.card().classes("pack-card pack-fade p-3 w-full")
			with ui_refs["card_feedback"]:
				with ui.row().classes("items-center w-full"):
					ui.icon("rule").classes("text-xl pack-text-primary")
					ui.label(t("packaging.current_step", "Feedback")).classes("ml-2 text-sm font-bold pack-text-primary")
					ui.space()
					ui_refs["feedback_badge"] = ui.badge("IDLE").classes("font-bold")
				ui.label("").classes("text-base font-semibold pack-text-primary mt-2 leading-snug") \
					.style("min-height: 56px;") \
					.bind_text_from(ctx.state, "work_feedback", backward=lambda n: str(n or ""))

		with ui.card().classes("pack-card pack-fade w-full p-4"):
			ui.label(t("packaging.job_data", "Container Data")).classes("text-base font-bold pack-text-primary mb-2")
			with ui.element("div").classes("w-full grid grid-cols-12 gap-3"):
				with ui.column().classes("gap-1 col-span-12 md:col-span-6"):
					ui.label(t("packaging.part_number", "Part Number")).classes("text-xs uppercase tracking-wide pack-text-secondary")
					ui.input().props("readonly standout").classes("w-full app-input").bind_value_from(
						ctx.state, "part_number", backward=lambda n: str(n or "")
					)
				with ui.column().classes("gap-1 col-span-12 md:col-span-6"):
					ui.label(t("packaging.description", "Description")).classes("text-xs uppercase tracking-wide pack-text-secondary")
					ui.input().props("readonly standout").classes("w-full app-input").bind_value_from(
						ctx.state, "description", backward=lambda n: str(n or "-")
					)

				with ui.column().classes("gap-1 col-span-12 md:col-span-6"):
					ui.label(t("packaging.container_number", "Container")).classes("text-xs uppercase tracking-wide pack-text-secondary")
					ui.input().props("readonly standout").classes("w-full app-input").bind_value_from(
						ctx.state, "container_number", backward=lambda n: str(n or "")
					)
				with ui.column().classes("gap-1 col-span-12 md:col-span-6"):
					ui.label(t("packaging.quantity", "Quantity")).classes("text-xs uppercase tracking-wide pack-text-secondary")
					with ui.row().classes("w-full items-center gap-2 flex-nowrap"):
						ui.input().props("readonly standout").classes("w-full text-center app-input") \
							.bind_value_from(ctx.state, "current_container_qty", backward=lambda n: str(n or "0"))
						ui.icon("east").classes("pack-text-secondary shrink-0")
						ui.input().props("readonly standout").classes("w-full text-center app-input") \
							.bind_value_from(ctx.state, "max_container_qty", backward=lambda n: str(n or "0"))

				with ui.column().classes("gap-1 col-span-12"):
					ui.label(t("packaging.last_serial_number", "Last Serial Number")).classes("text-xs uppercase tracking-wide pack-text-secondary")
					ui.input().props("readonly standout").classes("w-full app-input").bind_value_from(
						ctx.state, "last_serial_number", backward=lambda n: str(n or "")
					)

			with ui.row().classes("w-full items-center gap-2 mt-3"):
				ui.label(t("packaging.progress", "Fill Progress")).classes("text-sm font-semibold pack-text-primary")
				ui.space()
				ui_refs["qty_ratio"] = ui.label("0%").classes("text-sm font-bold pack-primary")
			ui_refs["qty_progress"] = ui.linear_progress(value=0.0).classes("w-full mt-1")

		with ui.row().classes("pack-card pack-fade w-full gap-3 justify-start p-3"):
			ui.button(t("common.remove", "Remove"), icon="delete", on_click=lambda: _publish_cmd("remove")) \
				.props("outline color=negative").classes("pack-btn w-[140px] h-[48px]")
			ui.button(t("common.print", "Print"), icon="print", on_click=lambda: _publish_cmd("print")) \
				.props("outline color=primary").classes("pack-btn w-[140px] h-[48px]")
			ui.button(t("common.new", "New"), icon="add", on_click=lambda: _publish_cmd("new")) \
				.props("outline color=positive").classes("pack-btn w-[140px] h-[48px]")
			ui.button(t("common.refresh", "Refresh"), icon="refresh", on_click=lambda: _publish_cmd("refresh")) \
				.props("outline color=secondary").classes("pack-btn w-[140px] h-[48px]")
			ui.button(t("common.reset", "Reset"), icon="restart_alt", on_click=lambda: _publish_cmd("reset")) \
				.props("outline color=warning").classes("pack-btn w-[140px] h-[48px]")

	add_timer(0.1, _drain_wait_open_signal)
	add_timer(0.1, _drain_wait_close_signal)
	add_timer(0.2, _apply_instruction_feedback_colors)
	add_timer(0.2, _apply_qty_progress)
	_apply_instruction_feedback_colors()
	_apply_qty_progress()
