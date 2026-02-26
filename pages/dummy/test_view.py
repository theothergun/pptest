from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Any, Optional

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from layout.app_style import button_classes, button_props

def render(container: ui.element, ctx: PageContext) -> None:
	"""Manual Dummy Test view:
	- left: switches for ctx.state.dummy_*
	- right: 2 write lanes + watch list
	"""

	# -----------------------------
	# helpers
	# -----------------------------
	def state_prop_names() -> list[str]:
		# Works well if ctx.state is a dataclass (your AppState is)
		if is_dataclass(ctx.state):
			return [f.name for f in fields(ctx.state)]
		# fallback
		return [k for k in dir(ctx.state) if not k.startswith('_') and not callable(getattr(ctx.state, k))]

	def dummy_props() -> list[str]:
		return [p for p in state_prop_names() if p.startswith("dummy_")]

	def writable_props() -> list[str]:
		# contains _result or _status (as requested)
		return [p for p in state_prop_names() if ("_result" in p or "_status" in p)]

	def get_type_and_value(prop: str) -> tuple[type, Any]:
		v = getattr(ctx.state, prop, None)
		return (type(v), v)

	def coerce_value(prop: str, raw: Any) -> Any:
		"""Convert UI raw value into the same type as ctx.state.<prop> (best-effort)."""
		current = getattr(ctx.state, prop, None)
		t = type(current)

		# bool
		if t is bool:
			return bool(raw)

		# None/untyped fallback: keep string
		if current is None:
			return raw

		# Decimal
		if isinstance(current, Decimal):
			try:
				return Decimal(str(raw).strip())
			except Exception:
				return current

		# int/float/str
		try:
			if t is int:
				return int(str(raw).strip())
			if t is float:
				return float(str(raw).strip())
			if t is str:
				return str(raw)
		except Exception:
			return current

		# default: try to keep raw
		return raw

	def emit(prop: str, value: Any) -> None:
		# topic naming consistent with your bridge subscription: "state.<prop>"
		ctx.bridge.emit_patch(f"{prop}", value)

	# -----------------------------
	# local UI state (per session)
	# -----------------------------
	writable = writable_props()
	if not writable:
		writable = [""]  # avoid empty options

	lane1_prop: str = writable[0]
	lane2_prop: str = writable[0] if len(writable) == 1 else writable[1]

	# store lane inputs separately (because UI control type changes)
	lane1_raw: Any = getattr(ctx.state, lane1_prop, "")
	lane2_raw: Any = getattr(ctx.state, lane2_prop, "")

	# watch list: prop -> last displayed value
	watch: dict[str, Any] = {}

	# -----------------------------
	# refreshables
	# -----------------------------
	@ui.refreshable
	def left_dummy_card() -> None:
		props = dummy_props()

		with ui.card().classes("w-[360px] h-full p-0 app-panel overflow-hidden flex flex-col"):
			with ui.row().classes("w-full items-center justify-between px-4 py-3").style(
				"background:var(--surface); border-bottom:1px solid var(--input-border);"
			):
				ui.label("Dummy properties").classes("text-sm font-semibold")
				ui.badge(str(len(props))).props("outline").classes("text-xs")

			# no scroll: keep it compact
			with ui.column().classes("w-full p-4 gap-3 flex-1").style(
				"background:var(--surface); color:var(--text-primary);"
			):
				if not props:
					ui.label("No dummy_* fields found on ctx.state").classes("text-sm opacity-70")
					return

				for p in props:
					t, v = get_type_and_value(p)

					with ui.row().classes("w-full items-center justify-between"):
						ui.label(p).classes("text-xs text-gray-600")

						if t is bool:
							def _on_change(e, prop=p):
								emit(prop, bool(e.value))

							ui.switch(value=bool(v), on_change=_on_change).props("color=primary")
						else:
							# if you ever add non-bool dummy_* fields, show a compact input
							def _on_change(e, prop=p):
								emit(prop, coerce_value(prop, e.value))

							ui.input(value=str(v) if v is not None else "", on_change=_on_change)\
								.props("dense outlined").classes("w-40 text-xs")

	@ui.refreshable
	def watch_section() -> None:
		with ui.card().classes("w-full flex-1 min-h-0 p-0 app-panel overflow-hidden flex flex-col"):

			#header fix
			with ui.row().classes("w-full items-center justify-between px-4 py-3").style(
				"background:var(--surface); border-bottom:1px solid var(--input-border);"
			):
				ui.label("Watch").classes("text-sm font-semibold")
				with ui.row().classes("items-center gap-2"):
					ui.button("Clear", icon="delete_sweep", on_click=lambda: (watch.clear(), watch_section.refresh()))\
						.props(button_props("danger") + " dense").classes(button_classes())

			#body (scrollable, fills rest)
			with ui.column().classes("w-full flex-1 min-h-0 overflow-auto p-3 gap-2").style(
				"background:var(--surface); color:var(--text-primary);"
			):
				if not watch:
					ui.label("No watched values yet. Use Write to add them.").classes("text-sm opacity-70")
					return

				for prop in list(watch.keys()):
					current_val = getattr(ctx.state, prop, None)
					watch[prop] = current_val  # keep updated display

					with ui.row().classes("w-full items-center justify-between px-3 py-2 rounded-xl").style(
						"border:1px solid var(--input-border); background:var(--surface-muted);"
					):
						with ui.column().classes("gap-0"):
							ui.label(prop).classes("text-xs text-gray-500")
							ui.label(str(current_val)).classes("text-sm font-semibold")

						ui.button(icon="close", on_click=lambda p=prop: (watch.pop(p, None), watch_section.refresh()))\
							.props("flat round dense").classes("text-gray-500")

	@ui.refreshable
	def input_section() -> None:
		nonlocal lane1_prop, lane2_prop, lane1_raw, lane2_raw

		def lane_row(lane: int) -> None:
			nonlocal lane1_prop, lane2_prop, lane1_raw, lane2_raw

			prop = lane1_prop if lane == 1 else lane2_prop
			current = getattr(ctx.state, prop, None)
			is_bool = isinstance(current, bool)

			def on_select_change(e) -> None:
				nonlocal lane1_prop, lane2_prop, lane1_raw, lane2_raw
				if lane == 1:
					lane1_prop = e.value
					lane1_raw = getattr(ctx.state, lane1_prop, False if isinstance(getattr(ctx.state, lane1_prop, None), bool) else "")
				else:
					lane2_prop = e.value
					lane2_raw = getattr(ctx.state, lane2_prop, False if isinstance(getattr(ctx.state, lane2_prop, None), bool) else "")
				input_section.refresh()

			with (ui.row().classes("w-full items-center gap-3")):
				ui.select(
					options=writable,
					value=prop,
					on_change=on_select_change,
				).props("dense outlined").classes("w-[280px]")

				if is_bool:
					def on_bool_change(e) -> None:
						nonlocal lane1_raw, lane2_raw
						if lane == 1:
							lane1_raw = bool(e.value)
						else:
							lane2_raw = bool(e.value)

					ui.switch(
						value=bool(lane1_raw) if lane == 1 else bool(lane2_raw),
						on_change=on_bool_change,
					).props("dense color=primary")
				else:
					def on_text_change(e) -> None:
						nonlocal lane1_raw, lane2_raw
						if lane == 1:
							lane1_raw = e.value
						else:
							lane2_raw = e.value

					ui.input(
						value=str(lane1_raw) if lane == 1 else str(lane2_raw),
						on_change=on_text_change,
					).props("dense outlined").classes("grow")

				ui.button(icon="save", on_click= lambda: write_clicked(lane)
						  ).props(button_props("secondary") + " dense").classes(button_classes())

		def write_clicked(lane = None) -> None:
			# write lane1
			if lane1_prop and lane is None or lane == 1:
				v1 = coerce_value(lane1_prop, lane1_raw)
				emit(lane1_prop, v1)
				watch.setdefault(lane1_prop, v1)

			# write lane2
			if lane2_prop  and lane is None or lane == 2:
				v2 = coerce_value(lane2_prop, lane2_raw)
				emit(lane2_prop, v2)
				watch.setdefault(lane2_prop, v2)

			watch_section.refresh()

		with ui.card().classes("w-full p-0 app-panel overflow-hidden"):
			with ui.row().classes("w-full items-center justify-between px-4 py-3").style(
				"background:var(--surface); border-bottom:1px solid var(--input-border);"
			):
				ui.label("Input").classes("text-sm font-semibold")

			with ui.column().classes("w-full p-4 gap-3").style("background:var(--surface); color:var(--text-primary);"):
				lane_row(1)
				lane_row(2)

				with ui.row().classes("w-full justify-end pt-1"):
					ui.button("Write", icon="save", on_click=write_clicked)\
						.props(button_props("primary") + " dense").classes(button_classes())

	def refresh_view():
		if watch:
			watch_section.refresh()

		left_dummy_card.refresh()

	# -----------------------------
	# layout (non-scrolling header)
	# -----------------------------
	def build_content(_parent: ui.element) -> None:
		with ui.column().classes("w-full h-screen min-h-0"):
			# fixed header
			#with ui.row().classes("w-full items-center justify-between px-5 py-3 bg-primary text-white"):
			#	ui.label("Manual Dummy Test").classes("text-base font-semibold")
			#	ui.icon("tune").classes("text-lg opacity-90")

			# body area
			with ui.row().classes("w-full flex-1 min-h-0 p-4 gap-4 rounded-2xl").style(
				"background:var(--surface-muted);"
			):
				# left (no scroll)
				left_dummy_card()

				# right (top input + bottom watch)
				with ui.column().classes("grow h-full min-h-0 flex flex-col gap-4"):
					input_section()
					watch_section()

		# Optional: keep watch values updated from ctx.state (even when updates come from elsewhere)
		ui.timer(0.5, refresh_view)

	build_page(ctx, container, title="Manual Test", content=build_content, show_action_bar=False)
