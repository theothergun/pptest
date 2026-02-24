from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from pages.dummy.historization import load_history_records
from pages.dummy.result_models import ResultsViewState


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _parse_iso_dt(s: str) -> Optional[datetime]:
	if not s:
		return None
	try:
		return datetime.fromisoformat(s.replace("Z", "+00:00"))
	except Exception:
		return None


def _fmt_dt(s: str) -> str:
	dt = _parse_iso_dt(s)
	if not dt:
		return s or "-"
	return dt.strftime("%Y-%m-%d %H:%M:%S")


def _chip_for_state(state_val: Any) -> tuple[str, str]:
	if state_val is True:
		return ("OK", "bg-green-100 text-green-700")
	if state_val is False:
		return ("NOK", "bg-red-100 text-red-700")
	return ("PENDING", "bg-gray-100 text-gray-600")


def _overall_state(results: Dict[str, Any]) -> Any:
	states = [v.get("state") for v in results.values() if isinstance(v, dict)]
	if any(s is False for s in states):
		return False
	if states and all(s is True for s in states):
		return True
	return None


def _range_text(d_from: date, d_to: date) -> str:
	return f"{d_from.isoformat()} → {d_to.isoformat()}"


def _d_to_q(d: date) -> str:
	return d.isoformat()


def _q_to_d(s: str) -> date:
	if "-" in s:
		y, m, d = (int(x) for x in s.split("-"))
		return date(y, m, d)
	y, m, d = (int(x) for x in s.split("/"))
	return date(y, m, d)


def date_range_selector(st: ResultsViewState) -> None:
	with ui.row().classes("items-end gap-2"):
		range_input = ui.input(
			label="Range",
			value=_range_text(st.date_from, st.date_to),
		).props("dense readonly").classes("w-[260px]")

		with ui.menu() as range_menu:
			def on_range_change(e) -> None:
				v = e.value or {}
				if "from" in v and "to" in v:
					st.date_from = _q_to_d(v["from"])
					st.date_to = _q_to_d(v["to"])
					range_input.value = _range_text(st.date_from, st.date_to)

			ui.date(
				value={"from": _d_to_q(st.date_from), "to": _d_to_q(st.date_to)},
				on_change=on_range_change,
			).props("range minimal")

		ui.button(icon="event", on_click=range_menu.open).props("flat round dense").classes("text-primary")


# ---------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------
def render(container: ui.element, ctx: PageContext, *, max_range_days: int = 31) -> None:
	# This is the missing piece in many NiceGUI layouts:
	# it gives the flex chain a real height to compute against.
	# ui.query("body").classes("h-screen overflow-hidden")

	def build_content(_parent: ui.element) -> None:
		available_set_names = [s.name for s in (ctx.dummy_controller.edition_state.sets or [])]
		st = ResultsViewState(max_range_days=max_range_days)

		def enforce_max_range() -> bool:
			if st.date_to < st.date_from:
				ui.notify("End date must be >= start date", type="warning")
				return False
			if (st.date_to - st.date_from).days > st.max_range_days:
				ui.notify(f"Max range is {st.max_range_days} days", type="warning")
				return False
			return True

		# --- refreshables (defined early, then callbacks call .refresh()) ---
		@ui.refreshable
		def left_header() -> None:
			ui.label("Loaded Executions").classes("text-sm font-semibold")
			ui.label(f"{len(st.records)}").classes("text-xs opacity-60")

		@ui.refreshable
		def left_list() -> None:
			if not st.records:
				ui.label("No results loaded").classes("px-3 py-3 text-sm opacity-60")
				return

			for i, r in enumerate(st.records):
				sel = (st.selected_index == i)
				row_cls = "w-full px-3 py-2 border-b cursor-pointer"
				row_style = "border-color:var(--input-border);"
				if sel:
					row_style += " background:var(--surface-muted);"

				started = _fmt_dt(str(r.get("started_at", "")))
				set_name = str(r.get("set_name", "-"))

				with ui.row().classes(row_cls).style(row_style).on("click", lambda _=None, idx=i: select_record(idx)):
					with ui.column().classes("grow min-w-0"):
						ui.label(set_name).classes("text-sm font-semibold truncate")
						ui.label(started).classes("text-xs opacity-70")

		@ui.refreshable
		def right_detail() -> None:
			if st.selected_index is None or st.selected_index >= len(st.records):
				ui.label("Select a result on the left").classes("text-sm opacity-60")
				return

			rec = st.records[st.selected_index]

			if st.mode == "raw":
				ui.code(json.dumps(rec, indent=2, ensure_ascii=False)).classes("w-full text-xs")
				return

			started = _fmt_dt(str(rec.get("started_at", "")))
			finished = _fmt_dt(str(rec.get("finished_at", "")))
			set_name = str(rec.get("set_name", "-"))

			with ui.row().classes("w-full items-center gap-3"):
				ui.label(set_name).classes("text-base font-semibold")
				ui.label(f"Start: {started}").classes("text-xs opacity-70")
				ui.label(f"End: {finished}").classes("text-xs opacity-70")

			ui.separator().classes("my-2")

			results = rec.get("results", {}) or {}
			if not results:
				ui.label("No result details available").classes("text-sm opacity-60")
				return

			for dummy_name, drec in results.items():
				drec = drec or {}
				state_val = drec.get("state")
				values = (drec.get("values") or {})

				with ui.expansion(dummy_name, icon="assignment", value=True).classes(
						"w-full rounded-xl border border-slate-200/60"):

					if not values:
						ui.label("No captured inspection values").classes("text-sm opacity-60")
					else:
						with ui.element("div").classes("w-full grid grid-cols-2 gap-x-4 gap-y-2"):
							for ins_name, val in values.items():
								ui.label(str(ins_name)).classes("text-sm opacity-80")
								ui.label(str(val)).classes("text-sm font-semibold")

		def refresh_all() -> None:
			left_header.refresh()
			left_list.refresh()
			right_detail.refresh()

		def do_load() -> None:
			if not enforce_max_range():
				return

			set_name = None if st.selected_set == "All" else st.selected_set
			records = load_history_records(date_from=st.date_from, date_to=st.date_to, set_name=set_name)

			def keyfn(r: Dict[str, Any]) -> datetime:
				dt = _parse_iso_dt(str(r.get("started_at", "")))
				return dt or datetime.min

			st.records = sorted(records, key=keyfn, reverse=True)
			st.selected_index = 0 if st.records else None
			refresh_all()

		def select_record(idx: int) -> None:
			st.selected_index = idx
			refresh_all()

		def set_mode(mode: str) -> None:
			st.mode = mode
			right_detail.refresh()

		# ---------------- ROOT (same idea as your working Config view) ----------------
		with ui.column().classes("w-full h-full min-h-0 flex flex-col overflow-hidden gap-3"):
			# HEADER (fixed)
			#with ui.row().classes(
			#		"w-full items-center justify-between px-4 py-2 bg-primary text-white rounded-xl shrink-0"):
			#	ui.label("Dummy Test Results").classes("text-base font-semibold")
			#	ui.icon("insights").classes("text-lg")

			# FILTER (fixed)
			with ui.card().classes("w-full p-3 rounded-xl border border-slate-200/60 shadow-sm shrink-0").style(
				"background:var(--surface); border-color:var(--input-border);"
			):
				with ui.row().classes("w-full items-end gap-3"):
					date_range_selector(st)

					set_opts = ["All"] + sorted(available_set_names)
					ui.select(
						options=set_opts,
						value=st.selected_set,
						on_change=lambda e: setattr(st, "selected_set", e.value),
					).props('dense label="Set"').classes("w-[260px]")

					ui.space()
					ui.button("Load", icon="refresh", on_click=do_load).props("unelevated").classes(
						"bg-primary text-white")

				ui.label(f"Max selectable range: {st.max_range_days} days").classes("text-xs opacity-60 pt-2")

			# BODY (fills remaining height)
			with ui.row().classes("w-full flex-1 min-h-0 overflow-hidden gap-3"):
				# LEFT CARD
				with ui.card().classes(
						"w-[360px] min-w-[360px] h-full overflow-hidden "
						"rounded-xl shadow-sm border border-slate-200/60 p-0 flex flex-col"
				).style("background:var(--surface); border-color:var(--input-border);"):
					with ui.row().classes(
							"w-full items-center justify-between px-3 py-2 border-b border-slate-200/60 shrink-0"
					).style("background:var(--surface); border-color:var(--input-border);"):
						left_header()

					# only this scrolls
					with ui.scroll_area().classes("w-full flex-1 min-h-0").style("background:var(--surface);"):
						left_list()

				# RIGHT CARD
				with ui.card().classes(
						"flex-1 h-full overflow-hidden rounded-xl shadow-sm border border-slate-200/60 p-0 flex flex-col"
				).style("background:var(--surface); border-color:var(--input-border);"):
					# fixed header
					with ui.row().classes(
							"w-full items-center justify-between px-3 py-2 border-b border-slate-200/60 shrink-0"
					).style("background:var(--surface); border-color:var(--input-border);"):
						ui.label("Details").classes("text-sm font-semibold")

						def mode_btn(icon: str, mode: str, tooltip: str) -> None:
							active = (st.mode == mode)
							cls = "text-primary" if active else "text-gray-400"
							ui.button(icon=icon, on_click=lambda: set_mode(mode)).props("flat round dense").classes(
								f"w-9 h-9 {cls}")
							ui.tooltip(tooltip).classes("text-xs")

						with ui.row().classes("items-center gap-1"):
							mode_btn("dashboard", "ui", "UI mode")
							mode_btn("data_object", "raw", "Raw JSON")

					# only this scrolls
					with ui.scroll_area().classes("w-full flex-1 min-h-0 p-3").style("background:var(--surface);"):
						right_detail()

		# Load once after the UI exists (so you actually see data without clicking)
		ui.timer(0.01, do_load, once=True)

	build_page(
		ctx,
		container,
		title="Test Results",
		content=build_content,
		show_action_bar=False,
	)
