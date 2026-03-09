# pages/home.py
import queue

from nicegui import ui
from loguru import logger

from layout.action_bar.models import Action
from layout.context import PageContext
from layout.page_scaffold import build_page
from pages.visual_inspection.dialog import create_failure_catalogue_dialog
from services.ui.view_action import make_action_event, publish_standard_view_action
from services.ui.view_cmd import view_wait_key

VISUAL_INSPECTION_CMD_KEY = "visual_inspection.cmd"
VISUAL_INSPECTION_NOX_VIEW = "visual_inspection_nox"
VISUAL_INSPECTION_NOX_WAIT_MODAL_KEY = view_wait_key(VISUAL_INSPECTION_NOX_VIEW)
from services.ui.registry import UiActionName, UiEvent, ViewName

BG_Q_CLASSES = {"bg-positive", "bg-warning", "bg-negative", "bg-info"}


def render(container: ui.element, ctx: PageContext) -> None:
	dialog, open_catalogue = create_failure_catalogue_dialog(ctx)

	# --- lifecycle management (same pattern as your Scripts Lab page) ---
	page_timers: list = []
	# page_subs: list = [] # use it in case you have multiple individual subscription
	sub_state = ctx.bridge.subscribe_many(["state.ltc_error_status", "state.vc_error_status"])

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		try:
			sub_state.close()
		except Exception:
			logger.warning("Failed to close visual-inspection state subscription during cleanup")

		for t in page_timers:
			try:
				t.cancel()
			except Exception:
				logger.warning("Failed to cancel visual-inspection timer during cleanup")
		page_timers[:] = []

	ctx.state._page_cleanup = cleanup
	ui.context.client.on_disconnect(cleanup)

	def _publish_cmd(cmd: str) -> None:
		publish_standard_view_action(
			worker_bus=ctx.worker_bus,
			view=ViewName.VI_HOME,
			cmd_key=VISUAL_INSPECTION_CMD_KEY,
			name=cmd,
			event=UiEvent.CLICK,
			wait_key=VISUAL_INSPECTION_NOX_WAIT_MODAL_KEY,
			source_id=VISUAL_INSPECTION_NOX_VIEW,
		)

	# listeners can be anywhere, but only need to be registered once per page build/render
	def on_action_clicked(action_id, action:Action):
		action_event = make_action_event(view=ViewName.VI_HOME, name=UiActionName(str(action_id)), event=UiEvent.CLICK)
		action_name = action_event["name"]

		# example behavior: toggle active state
		if ctx.action_bar:
			# ctx.action_bar.set_active(action_id, not action.is_active)

			# example: enable "save" after refresh is active
			if action_id == UiActionName.START_STOP.value:
				ui.notify(f"clicked: {action_id}")
				# ctx.action_bar.set_active(action_id, not action.is_active)
				cmd = UiActionName.STOP if action.is_active else UiActionName.START
				ctx.action_bar.update(action_id, active=not action.is_active)
				ctx.action_bar.set_enabled("unlock", not action.is_active)
				_publish_cmd(cmd)

			if action_name == UiActionName.LTC_STATUS.value:
				ctx.set_state_and_publish("ltc_error_status", (ctx.state.ltc_error_status+1)%4)
				ui.notify(f"new ltc status = {ctx.state.ltc_error_status}")

			if action_name == UiActionName.VC_STATUS.value:
				#ctx.state.vc_error_status = (ctx.state.vc_error_status+1)%4
				ctx.set_state_and_publish("vc_error_status", (ctx.state.vc_error_status + 1) % 4)
				ui.notify(f"new vc status = {ctx.state.vc_error_status}")

			if action_name == UiActionName.FAILURE_CATALOGUE.value:
				ui.notify("failures")
				open_catalogue(sn="1234567", pn="ABC-999")

			if action_name == UiActionName.UNLOCK.value:
				#ctx.state.ltc_leak_rate +=1
				ctx.set_state_and_publish("ltc_leak_rate", (ctx.state.vc_error_status + 1) % 4)

	def build_content(_parent: ui.element) -> None:
		# Root: 2 rows (top / middle / bottom)
		with ui.column().classes("w-full h-screen box-border gap-4 px-6 pb-4 pt-0 overflow-hidden"):
			# ── Row 1: Centered text block, Counters card aligned right ─────────────────────────────────────
			# ── Row 1: Centered instruction/progress panels + Counters card right ─────────────────────────
			with ui.row().classes("w-full flex-1 relative"):
				# Instruction + progress styled like screenshot, centered
				# (we keep absolute centering like your original)
				with ui.column().classes(
						"absolute left-1/2 top-25 -translate-x-1/2 -translate-y-1/2 items-center gap-4 pr-[230px]"):
					# INSTRUCTION PANEL
					instruction_panel = ui.card().classes(
						"w-[900px] rounded-2xl overflow-hidden p-0 bg-gray-800 shadow"
					)
					with instruction_panel:
						with ui.row().classes("w-full items-stretch relative"):
							# left stripe
							ui.element("div").classes("w-[14px] bg-info")
							# content
							with ui.column().classes("flex-1 px-6 py-4"):
								ui.label("INSTRUCTION FOR WORKER").classes("text-[11px] text-primary font-semibold")
								work_instruction = ui.label().classes("text-xl font-semibold leading-snug")
								work_instruction.bind_text_from(ctx.state, "work_instruction",
																backward=lambda n: str(n))

					# right tag
					# ui.label("INFO").classes("absolute right-5 top-4 text-xs bg-blue-500 text-white px-3 py-1 rounded-lg")

					# PROGRESS PANEL
					progress_panel = ui.card().classes(
						"w-[900px] rounded-2xl overflow-hidden p-0 bg-gray-800 shadow"
					)
					with progress_panel:
						with ui.row().classes("w-full items-stretch relative"):
							# left stripe
							progress_stripe = ui.element("div").classes("w-[14px] bg-yellow-400")
							with ui.column().classes("flex-1 px-6 py-4"):
								ui.label("FEEDBACK").classes("text-[11px] text-primary font-semibold")
								work_progress = ui.label().classes("text-[17px] font-semibold leading-snug")
								work_progress.bind_text_from(ctx.state, "work_feedback", backward=lambda n: str(n))

				# ui.label("WARN").classes(
				#	"absolute right-5 top-4 text-xs bg-blue-500 text-white px-3 py-1 rounded-lg"
				# )

				# Counters card aligned right (OLD CARD BACK, height matches the two panels area)
				with ui.row().classes("w-full items-start"):
					# Height math: 2 panels (~72px each content + paddings) + gap (~16px) ~= 170-190px
					# Pick a fixed height so it visually matches the instruction+progress stack.
					with ui.card().classes("ml-auto w-[220px] h-[190px] p-0"):
						# header bar
						with ui.row().classes("w-full h-[35px] bg-gray-200 px-3 py-1 rounded-t"):
							ui.label("Counters").classes("text-lg font-semibold mb-1")
						# body
						body = ui.row().classes("w-full")
						_add_card_entries(body, {
							"part_good": {"label": "Good", "icon": "check_circle", "color": "text-positive"},
							"part_bad": {"label": "Bad", "icon": "cancel", "color": "text-negative"},
							"part_total": {"label": "Total", "icon": "functions", "color": "text-info"}})

			# ── Row 2: Left card, optional center picture section, right card ─────────
			with ui.row().classes('w-full h-[200px] items-stretch justify-between gap-6'):
				ltc_card = ui.card().classes("w-[400px] h-full p-0")
				with ltc_card:
					# header
					with ui.row().classes("w-full h-[35px] bg-gray-200 px-3 py-1 rounded-t"):
						ui.label("Leak Test").classes("text-lg font-semibold")
					# body
					body = ui.row()
					_add_card_entries(body, {
						"ltc_dmc": {"label": "Serial number", "icon": "qr_code_2", "color": "text-black"},
						"ltc_status": {"label": "Progress", "icon": "autorenew", "color": "text-black"},
						"ltc_leak_rate": {"label": "Leak rate", "icon": "speed", "color": "text-black"},
						"ltc_result": {"label": "Result", "icon": "task_alt", "color": "text-black"}}, "text-black")

				# Center section (can be shown/hidden later)
				center_section = ui.column().classes('flex-1 items-center justify-center')
				with center_section:
					ui.label('Picture area').classes('text-gray-500')
				# Example placeholder; swap to ui.image('...') later
				# ui.image('path_or_url').classes('max-h-64 object-contain')

				vc_card = ui.card().classes("w-[400px] h-full p-0 ml-auto")
				with vc_card:
					# header
					with ui.row().classes("w-full h-[35px] bg-gray-200 px-3 py-1 rounded-t"):
						ui.label("Visual control").classes("text-lg font-semibold")
					# body
					body = ui.row()
					_add_card_entries(body, {
						"vc_dmc": {"label": "Serial number", "icon": "qr_code_2", "color": "text-black"},
						"vc_result": {"label": "Result", "icon": "task_alt", "color": "text-black"}}, "text-black")

		# update ltc color
		def update_ltc_color(status=0) -> None:
			ltc_color = _get_bg_color(status)
			update_bg_color([progress_stripe, ltc_card], ltc_color)

		# update vc color
		def update_vc_color(status=0) -> None:
			vc_color = _get_bg_color(status)
			update_bg_color([vc_card], vc_color)

		def update_bg_color(elements: list[ui.element], color: str):
			for elem in elements:
				elem.classes(remove=" ".join(BG_Q_CLASSES))
				elem.classes(color)

		def initialize_colors():
			update_ltc_color(status=ctx.state.ltc_error_status)
			update_vc_color(status=ctx.state.vc_error_status)

		# read the bus to get any available changes and make extra reaction to them like updating styles
		def _drain_bus() -> None:
			while True:
				try:
					msg = sub_state.queue.get_nowait()
					key = msg.topic.replace("state.", "")
					if key == "ltc_error_status":
						update_ltc_color(msg.payload[key])
					if key == "vc_error_status":
						update_vc_color(msg.payload[key])

				# ui.notify(msg)
				except queue.Empty:
					break

		add_timer(0.1, _drain_bus)

		initialize_colors()

	def _add_card_entries(
			parent: ui.element,
			data: dict[str, str | dict],
			text_color: str = "text-gray-600",
	) -> None:
		"""
		data: {"state_key": "Label",
			"state_key2": {"label": "Good", "icon": "check_circle", "value_color": "text-green-600"}, }
		"""
		with parent.classes("w-full gap-2 px-1 py-1"):
			for key, spec in data.items():
				# defaults
				label_text = spec if isinstance(spec, str) else spec.get("label", str(key))
				icon_name = None if isinstance(spec, str) else spec.get("icon")
				color = "" if isinstance(spec, str) else spec.get("color", "")

				with ui.row().classes("w-full items-center justify-between leading-none px-2 pb-2"):
					# left: (optional) icon + label
					with ui.row().classes("items-center gap-2"):
						if icon_name:
							ui.icon(icon_name).classes(f"text-base {color}")
						ui.label(label_text).classes(f"text-[15px] {text_color} m-0 leading-none")

					# right: value
					ui.label().classes(f"text-xl font-bold m-0 leading-none {color}") \
						.bind_text_from(ctx.state, key, backward=lambda n: str(n))

	def _get_bg_color(status: int):
		# status: 0 = init, 1= working, 2 = success, 3 = error
		# bg-orange-8 = working bg-red-8 = error
		return "bg-%s" % ("positive" if status == 1 else "warning" if status == 2
		else "negative" if status == 3 else "info")

	build_page(ctx, container, content=build_content,
			   show_action_bar=True, on_action_clicked=on_action_clicked)
