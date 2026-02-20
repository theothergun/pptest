from __future__ import annotations

import queue
from typing import Any

from nicegui import ui
from layout.context import PageContext
from services.i18n import t
from services.app_config import get_app_config
from services.ui_theme import get_theme_color
from services.ui.view_cmd import install_wait_dialog, publish_view_cmd, view_wait_key


PACKAGING_CMD_KEY = "packaging.cmd"
PACKAGING_NOX_VIEW = "packaging_nox"
PACKAGING_NOX_WAIT_MODAL_KEY = view_wait_key(PACKAGING_NOX_VIEW)


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
		publish_view_cmd(
			worker_bus=worker_bus,
			view=PACKAGING_NOX_VIEW,
			cmd_key=PACKAGING_CMD_KEY,
			cmd=cmd,
			wait_key=PACKAGING_NOX_WAIT_MODAL_KEY,
			open_wait=wait_dialog["open"],
			source_id=PACKAGING_NOX_VIEW,
		)

	wait_dialog = install_wait_dialog(
		ctx=ctx,
		worker_bus=worker_bus,
		wait_key=PACKAGING_NOX_WAIT_MODAL_KEY,
		title=t("packaging.wait_title", "Please wait"),
		message=t("packaging.working", "Working ..."),
		add_timer=add_timer,
	)

	def _set_counter_cards_color(current_qty: int, max_qty: int) -> None:
		# rules:
		# - red if both 0
		# - orange if 0 < current < max (or max == 0 but current > 0)
		# - green if max > 0 and current >= max
		if current_qty == 0 and max_qty == 0:
			bg = get_theme_color(cfg, "negative", "#DC2626")
		elif max_qty > 0 and current_qty >= max_qty:
			bg = get_theme_color(cfg, "status-good", "#86EFAC")
		else:
			bg = get_theme_color(cfg, "status-warning", "#FDBA74")
		text_color = "#FFFFFF" if bool(getattr(cfg.ui.navigation, "dark_mode", False)) else "#000000"

		card_a = ui_refs.get("card_current_qty")
		card_b = ui_refs.get("card_max_qty")
		if card_a is not None:
			try:
				card_a.style("background-color: %s; color: %s;" % (bg, text_color))
			except Exception:
				pass
		if card_b is not None:
			try:
				card_b.style("background-color: %s; color: %s;" % (bg, text_color))
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
	ui.add_head_html("""
<style>
.pack-shell {
	background: linear-gradient(135deg, var(--surface-muted) 0%, var(--app-background) 100%);
	border-radius: 20px;
	border: 1px solid var(--input-border);
	box-shadow: 0 12px 30px rgba(16, 24, 40, 0.06);
}
.pack-card {
	border: 1px solid var(--input-border);
	border-radius: 16px;
	box-shadow: 0 10px 24px rgba(16, 24, 40, 0.08);
	background: var(--surface);
	color: var(--text-primary);
	overflow: hidden;
}
.pack-soft {
	background: var(--surface);
	border: 1px solid var(--input-border);
}
.pack-qty {
	background: var(--surface-muted);
	border: 1px solid var(--input-border);
	box-shadow: 0 6px 14px rgba(16, 24, 40, 0.08);
}
.pack-qty .qty-value { color: var(--text-primary); }
.pack-qty .qty-label { color: var(--text-secondary); }
.dark .pack-qty,
.body--dark .pack-qty {
	background: rgba(255, 255, 255, 0.08);
	border-color: rgba(255, 255, 255, 0.22);
}
.dark .pack-qty .qty-value,
.body--dark .pack-qty .qty-value {
	color: #ffffff;
}
.dark .pack-qty .qty-label,
.body--dark .pack-qty .qty-label {
	color: rgba(255, 255, 255, 0.72);
}
.pack-panel {
	background: linear-gradient(180deg, var(--surface-muted) 0%, var(--surface) 100%);
	border: 1px solid var(--input-border);
	box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}
.pack-panel .panel-title {
	font-size: 11px;
	letter-spacing: 0.08em;
	text-transform: uppercase;
	color: var(--primary);
	font-weight: 700;
}
.pack-fade {
	animation: packFadeIn 220ms ease-out;
}
.pack-btn {
	font-weight: 700;
	letter-spacing: 0.3px;
	border-radius: 14px;
	transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
}
.pack-btn:hover {
	transform: translateY(-1px);
	box-shadow: 0 10px 20px rgba(15, 23, 42, 0.12);
}
.pack-header {
	min-height: 62px;
}
.pack-kpi {
	border-radius: 14px;
	border: 1px solid var(--input-border);
	background: var(--surface);
}
.pack-kpi .q-icon { font-size: 18px; }
@keyframes packFadeIn {
	from { opacity: 0; transform: translateY(6px); }
	to { opacity: 1; transform: translateY(0); }
}
</style>
""")

	with ui.column().classes("pack-shell w-full flex flex-col p-4 gap-3"):
		with ui.row().classes("w-full items-center gap-3 pack-header"):
			ui.icon("inventory_2").classes("text-amber-500 text-3xl")
			ui.label(t("packaging.title", "Packaging Station")).classes("text-2xl font-bold")
			ui.space()
			with ui.row().classes("items-center gap-2"):
				with ui.card().classes("pack-kpi px-4 py-2"):
					with ui.row().classes("items-center gap-2"):
						ui.icon("check_circle").classes("text-green-600")
						ui.label(t("packaging.total_good", "Good")).classes("text-sm text-gray-600")
					ui.label("").classes("text-2xl font-bold text-green-600") \
						.bind_text_from(ctx.state, "part_good", backward=lambda n: "%s" % int(n or 0))
				with ui.card().classes("pack-kpi px-4 py-2"):
					with ui.row().classes("items-center gap-2"):
						ui.icon("cancel").classes("text-red-600")
						ui.label(t("packaging.total_bad", "Bad")).classes("text-sm text-gray-600")
					ui.label("").classes("text-2xl font-bold text-red-600") \
						.bind_text_from(ctx.state, "part_bad", backward=lambda n: "%s" % int(n or 0))
				ui.button(t("common.reset", "Reset"), icon="restart_alt", on_click=lambda: _publish_cmd("reset_counters")) \
					.props("outline color=secondary").classes("pack-btn h-[40px] px-4")

		with ui.grid().classes("w-full gap-3").style("grid-template-columns: 280px 1fr;"):
			with ui.card().classes("pack-card pack-fade w-full p-4"):
				with ui.row().classes("w-full gap-3 flex-nowrap items-start"):
					with ui.column().classes("flex-grow gap-2"):
						ui.label(t("packaging.container_number", "Containernumber")).classes("text-xs uppercase tracking-wide text-gray-500")
						ui.label("").classes("text-lg font-bold") \
							.bind_text_from(ctx.state, "container_number", backward=lambda n: str(n or ""))

						ui.separator()

						ui.label(t("packaging.part_number", "Partnumber")).classes("text-xs uppercase tracking-wide text-gray-500")
						ui.label("").classes("text-lg font-bold") \
							.bind_text_from(ctx.state, "part_number", backward=lambda n: str(n or ""))

						ui.separator()

						ui.label(t("common.description", "Description")).classes("text-xs uppercase tracking-wide text-gray-500")
						ui.label("").classes("text-base") \
							.bind_text_from(ctx.state, "description", backward=lambda n: str(n or ""))
						with ui.row().classes("w-full gap-3 mt-1 flex-nowrap"):
							ui_refs["card_current_qty"] = ui.card().classes("pack-qty w-[120px] h-[64px] flex flex-col items-center justify-center")
							with ui_refs["card_current_qty"]:
								ui.label("").classes("qty-value text-2xl font-bold leading-none text-center") \
									.bind_text_from(ctx.state, "current_container_qty", backward=lambda n: "%s" % int(n or 0))
								ui.label(t("common.current", "Current")).classes("qty-label text-[10px] font-semibold tracking-wide leading-none text-center")

							ui_refs["card_max_qty"] = ui.card().classes("pack-qty w-[120px] h-[64px] flex flex-col items-center justify-center")
							with ui_refs["card_max_qty"]:
								ui.label("").classes("qty-value text-2xl font-bold leading-none text-center") \
									.bind_text_from(ctx.state, "max_container_qty", backward=lambda n: "%s" % int(n or 0))
								ui.label(t("common.max", "Max")).classes("qty-label text-[10px] font-semibold tracking-wide leading-none text-center")

			with ui.column().classes("w-full gap-3"):
				ui_refs["card_instruction"] = ui.card().classes("pack-card pack-panel pack-fade w-full p-4")
				with ui_refs["card_instruction"]:
					ui.label(t("packaging.instruction_for_worker", "Instruction for worker")).classes("panel-title")
					lbl_instruction = ui.label("").classes("text-xl font-semibold")
					lbl_instruction.style("min-height: 72px;")
					lbl_instruction.bind_text_from(ctx.state, "work_instruction", backward=lambda n: str(n or ""))

				ui_refs["card_feedback"] = ui.card().classes("pack-card pack-panel pack-fade w-full p-4")
				with ui_refs["card_feedback"]:
					ui.label(t("packaging.current_step", "Current step")).classes("panel-title")
					lbl_step = ui.label("").classes("text-xl font-semibold")
					lbl_step.style("min-height: 72px;")
					lbl_step.bind_text_from(ctx.state, "work_feedback", backward=lambda n: str(n or ""))

		with ui.row().classes("w-full gap-3 justify-start"):
			ui.button(t("common.start", "Start"), icon="play_arrow", on_click=lambda: _publish_cmd("start")) \
				.props("outline color=positive").classes("pack-btn w-[160px] h-[52px]")
			ui.button(t("common.stop", "Stop"), icon="stop", on_click=lambda: _publish_cmd("stop")) \
				.props("outline color=negative").classes("pack-btn w-[160px] h-[52px]")
			ui.button(t("common.reset", "Reset"), icon="restart_alt", on_click=lambda: _publish_cmd("reset")) \
				.props("outline color=info").classes("pack-btn w-[160px] h-[52px]")
			ui.button(t("common.refresh", "Refresh"), icon="refresh", on_click=lambda: _publish_cmd("refresh")) \
				.props("outline color=secondary").classes("pack-btn w-[160px] h-[52px]")

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
