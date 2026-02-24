# nicegui_dummy_edition.py
#
# A NiceGUI view roughly mirroring your XAML layout:
# - Header: Set selector + action icon buttons (add/delete/rename/save/import/export/scheduler/delete all/discard)
# - Body: two panes
#   - Left: "Dummy" list with add + select-all + delete-selected
#   - Right: "Station/Inspection" table with editable cells on selected row + per-row select/edit/delete
#
# Run:  python nicegui_dummy_edition.py
#
from __future__ import annotations

import json
from dataclasses import fields
from typing import  Any

from nicegui import ui
from layout.context import PageContext
from layout.page_scaffold import build_page
from pages.dummy.config_models import (DummySet, DummyTest, Inspection, TYPE_LIST,
									   DummyEditionState, CONFIG_FILE, save_config_file, load_config_file,
									   dict_to_sets, get_state_payload)
from pages.dummy.dialogs import confirm_dialog, prompt_dialog, import_dialog, create_msg_dialog, scheduler_dialog
from services.app_state import AppState


def render(container: ui.element, ctx: PageContext) -> None:
	APP_VARIABLES = [f.name for f in fields(AppState) if (f.name.startswith("dummy_")
					or f.name.endswith("result") or f.name.endswith("status"))]
	dialog, show_msg_dialog = create_msg_dialog()
	state = DummyEditionState()

	#try to load from dummy_config.json
	try:
		if CONFIG_FILE.exists():
			load_config_file(state)
			state.selected_set = state.sets[0] if state.sets else None
	except Exception as e:
		ui.notify(f"Failed to load dummy_config.jsn: {e}", type = "negative")
		print("dummy config not found")

	def build_content(_parent: ui.element) -> None:
		with ui.column().classes("w-full h-full overflow-hidden gap-0"):
			header_area()
			body_area()

	# -----------------------------
	# Small UI helpers
	# -----------------------------
	def icon_btn(icon: str, tooltip: str, on_click, *, enabled: bool = True, active_color: str | None = None) -> ui.button:
		DEFAULT = "primary"
		DISABLED = "grey-5"  # consistent disabled color (Quasar)

		with ui.button(icon=icon, on_click=on_click).props("flat round dense").classes(
				"w-9 h-9 p-0 flex items-center justify-center text-[16px]"
		) as b:
			ui.tooltip(tooltip).style("font-size: 13px; padding:8px")

		if enabled:
			b.enable()
			b.props(f"text-color={active_color or DEFAULT}")
		else:
			b.disable()
			b.props(f"text-color={DISABLED}")

		return b


	# -----------------------------
	# Actions (header)
	# -----------------------------
	def refresh_all() -> None:
		header_area.refresh()
		body_area.refresh()

	def set_add() -> None:
		next_id = max(s.id for s in state.sets) + 1 if state.sets else 1

		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			state.sets.append(DummySet(id=next_id, name=name.strip(), dummies=[]))
			state.selected_set = state.sets[-1]
			state.selected_dummy_id = None
			state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		prompt_dialog("Add Set", "Set name", f"Set {next_id}", _ok)

	def set_delete() -> None:
		if len(state.sets) <= 1:
			ui.notify("Cannot delete the last set", type="warning")
			return

		def _yes() -> None:
			current = state.selected_set
			state.sets = [s for s in state.sets if s.id != current.id]
			state.selected_set = state.sets[0]
			state.selected_dummy_id = None
			state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		confirm_dialog("Delete Set", f"Delete '{state.selected_set.name}'?", _yes)

	def set_rename() -> None:
		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			state.selected_set.name = name.strip()
			state.recompute_dirty()
			header_area.refresh()#refresh_all()

		prompt_dialog("Rename Set", "Set name", state.selected_set.name, _ok)

	def set_save() -> None:
		# hook this to your backend save
		try:
			save_config_file(state)
			state.commit()
			refresh_all()
			ui.notify("Saved", type="positive")
		except Exception as e:
			ui.notify(f"Save failed: {e}",type='negative')

	def set_discard_changes() -> None:
		def _yes() -> None:
			# for demo: just clear change flag
			state.rollback()
			refresh_all()
			ui.notify("Changes discarded", type="info")

		confirm_dialog("Discard Changes", "Discard unsaved changes?", _yes)

	def set_delete_all() -> None:
		if len(state.sets) <= 1:
			ui.notify("Nothing to delete", type="warning")
			return

		def _yes() -> None:
			state.sets = [state.selected_set]
			state.recompute_dirty()
			refresh_all()
			ui.notify("Other sets deleted", type="info")

		confirm_dialog("Delete All Sets", "Delete all sets except the current one?", _yes)

	def import_config() -> None:
		def _yes(data):
			state.sets = dict_to_sets(data)
			state.selected_set = state.sets[0] if state.sets else None
			state.selected_dummy_id = None
			state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()
		import_dialog(_yes,show_msg_dialog)

	def export_config() -> None:
		try:
			payload = get_state_payload(state)
			content = json.dumps(payload, indent=2).encode("utf-8")

			# NiceGUI download (content-based)
			ui.download(content, filename=f"dummy_config_export.json")
		except Exception as e:
			ui.notify(f"Export failed: {e}", type="negative")

	def scheduler_config() -> None:
		def _ok(new_settings) -> None:
			state.scheduler = new_settings
			# if you have dirty tracking: state.recompute_dirty()
			state.recompute_dirty()
			refresh_all()
			title = "Dummy Execution Configuration"
			if state.has_changes:
				show_msg_dialog(title,"Scheduler Settings updated (remember to Save).",mode="warning")

		scheduler_dialog(state.scheduler, _ok)


	# -----------------------------
	# Actions (dummy pane)
	# -----------------------------
	def dummy_add() -> None:
		next_id = max((d.id for d in state.dummies), default=0) + 1

		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			state.dummies.append(DummyTest(id=next_id, name=name.strip(), inspections=[]))
			state.selected_dummy_id = next_id
			state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		prompt_dialog("Add Dummy", "Dummy name", f"Dummy {next_id:03d}", _ok)

	def dummy_rename(dummy: DummyTest) -> None:
		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			dummy.name = name.strip()
			state.recompute_dirty()
			refresh_all()

		prompt_dialog("Rename Dummy", "Dummy name", dummy.name, _ok)

	def dummy_delete(dummy: DummyTest) -> None:
		def _yes() -> None:
			state.selected_set.dummies = [d for d in state.dummies if d.id != dummy.id]
			if state.selected_dummy_id == dummy.id:
				state.selected_dummy_id = None
				state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		confirm_dialog("Delete Dummy", f"Delete '{dummy.name}'?", _yes)

	def dummy_toggle_select_all() -> None:
		all_selected = state.all_dummy_selected()
		for d in state.dummies:
			d.is_checked = not all_selected
		refresh_all()

	def dummy_delete_selected() -> None:
		if not state.any_dummy_selected():
			return

		def _yes() -> None:
			to_delete = {d.id for d in state.dummies if d.is_checked}
			state.selected_set.dummies = [d for d in state.dummies if d.id not in to_delete]
			if state.selected_dummy_id in to_delete:
				state.selected_dummy_id = None
				state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		confirm_dialog("Delete Selected Dummies", "Delete all selected dummies?", _yes)

	def dummy_toggle_one(dummy: DummyTest) -> None:
		dummy.is_checked = not dummy.is_checked
		refresh_all()

	# -----------------------------
	# Actions (station pane)
	# -----------------------------
	def inspection_add() -> None:
		d = state.selected_dummy()
		if not d:
			ui.notify("Select a dummy first", type="warning")
			return

		next_id = max((s.id for s in d.inspections), default=0) + 1

		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			d.inspections.append(
				Inspection(
					id=next_id,
					name=name.strip(),
					state_field_name="PLC.Var.New",
					expected_value="",
					type_of_value=TYPE_LIST[0],
				)
			)
			state.selected_inspection_id = next_id
			state.recompute_dirty()
			refresh_all()

		prompt_dialog("Add Inspection", "Inspection name", f"Inspection {next_id}", _ok)

	def inspection_rename(st: Inspection) -> None:
		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			st.name = name.strip()
			state.recompute_dirty()
			refresh_all()

		prompt_dialog("Rename Inspection", "Inspection name", st.name, _ok)

	def inspection_delete(st: Inspection) -> None:
		d = state.selected_dummy()
		if not d:
			return

		def _yes() -> None:
			d.inspections = [x for x in d.inspections if x.id != st.id]
			if state.selected_inspection_id == st.id:
				state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		confirm_dialog("Delete Inspection", f"Delete '{st.name}'?", _yes)

	def inspection_toggle_select_all() -> None:
		d = state.selected_dummy()
		if not d:
			return
		all_selected = state.all_inspection_selected()
		for s in d.inspections:
			s.is_checked = not all_selected
		refresh_all()

	def inspection_toggle_one(st: Inspection) -> None:
		st.is_checked = not st.is_checked
		refresh_all()

	def inspection_delete_selected() -> None:
		d = state.selected_dummy()
		if not d or not state.any_inspection_selected():
			return

		def _yes() -> None:
			to_delete = {s.id for s in d.inspections if s.is_checked}
			d.inspections = [s for s in d.inspections if s.id not in to_delete]
			if state.selected_inspection_id in to_delete:
				state.selected_inspection_id = None
			state.recompute_dirty()
			refresh_all()

		confirm_dialog("Delete Selected Inspections", "Delete all selected inspections?", _yes)


	# -----------------------------
	# UI
	# -----------------------------
	#ui.colors(primary="#2D3B4F")  # subtle header-ish vibe

	@ui.refreshable
	def header_area() -> None:
		with ui.row().classes(
				"w-full items-center justify-between px-6 py-4 "
				"border-b rounded-t-2xl"
		).style("background:linear-gradient(90deg,var(--surface-muted),var(--surface)); border-color:var(--input-border);"):

			# LEFT: Set select
			set_names = [s.name for s in state.sets]
			current_name = state.selected_set.name if state.selected_set else None

			def on_set_change(e: Any) -> None:
				name = e.value
				s = next((x for x in state.sets if x.name == name), None)
				if s:
					state.selected_set = s
					state.selected_dummy_id = None
					state.selected_station_id = None
					state.recompute_dirty()
					refresh_all()

			ui.select(
				options=set_names,
				value=current_name,
				on_change=on_set_change,
			).props("outlined dense").classes("w-[420px]")

			# RIGHT: Action icons
			with ui.row().classes("items-center gap-1"):
				icon_btn("add", "Add set", set_add, active_color='green')
				icon_btn("delete", "Delete set", set_delete)
				icon_btn("edit", "Rename set", set_rename, active_color='orange')

				icon_btn("save", "Save", set_save, enabled=state.has_changes,
						 active_color="negative")
				icon_btn("restore","Discard changes", set_discard_changes, enabled=state.has_changes)

				icon_btn("file_upload","Import", import_config)
				icon_btn("file_download","Export", export_config, enabled=state.is_exportable())
				icon_btn("schedule","Scheduler", scheduler_config)

				icon_btn("delete_sweep","Delete all sets", set_delete_all,
				enabled=(len(state.sets) > 1), active_color="negative")


	@ui.refreshable
	def dummy_list_area() -> None:
		if not state.dummies:
			ui.label("No dummies in this set").classes("px-4 py-4 text-sm opacity-70")
			return

		with ui.column().classes("w-full"):
			for d in state.dummies:
				is_selected_row = (state.selected_dummy_id == d.id)
				selection_mode_active = state.any_dummy_selected()

				row_cls = (
					"w-full px-4 py-3 flex items-center gap-2 "
					"border-b transition-colors"
				)
				if is_selected_row:
					row_cls += " bg-[var(--surface-muted)]"

				with ui.row().classes(row_cls).style("border-color:var(--input-border);"):
					# name / select row
					ui.label(d.name).classes("grow font-medium cursor-pointer").on(
						"click",
						lambda _=None, did=d.id: (
							setattr(state, "selected_dummy_id", did),
							setattr(state, "selected_station_id", None),
							refresh_all(),
						),
					)

					# action icons on right
					if is_selected_row and not selection_mode_active:
						icon_btn("edit", "Rename dummy", lambda dd=d: dummy_rename(dd),
								 active_color="orange")
						icon_btn("check_box" if d.is_checked else "check_box_outline_blank", "Select dummy",
								 lambda dd=d: dummy_toggle_one(dd))
						icon_btn("delete", "Delete dummy", lambda dd=d: dummy_delete(dd),
								 active_color="negative")
					else:
						if selection_mode_active:
							icon_btn("check_box" if d.is_checked else "check_box_outline_blank", "Select dummy",
									 lambda dd=d: dummy_toggle_one(dd))
						else:
							ui.space().classes("w-12")

	@ui.refreshable
	def inspection_table_area() -> None:
		d = state.selected_dummy()
		if not d:
			ui.label("Select a dummy on the left to see inspections").classes("px-4 py-6 text-sm opacity-70")
			return

		# Sticky header (stays visible while scrolling inside the scroll_area)
		with ui.element("div").classes(
				"w-full px-4 py-3 text-sm font-semibold gap-4"
				"border-b sticky top-0 z-10" + " grid grid-cols-[27%_22%__22%_16%_1fr]"
		).style("background:var(--surface-muted); border-color:var(--input-border);"):

			ui.label("Inspection Name").classes("opacity-80 justify-start")
			ui.label("App Variable").classes("opacity-80")
			ui.label("Expected Value").classes("opacity-80 justify-start")
			ui.label("Type").classes("opacity-80 justify-start")
			ui.label("").classes("text-right")

		# Rows
		for i, insp in enumerate(d.inspections):
			is_row_selected = (state.selected_inspection_id == insp.id)
			selection_mode_active = state.any_inspection_selected()

			base = "w-full px-4 py-1 border-b items-center transition-colors duration-150"
			zebra = " bg-[var(--surface)]" if i % 2 else " bg-[var(--surface-muted)]"
			hover = " hover:brightness-95"
			selected = " bg-[var(--surface-muted)]" if is_row_selected else ""
			with ui.element('div').classes(base + zebra + hover + selected + " grid grid-cols-[27%_22%_22%_16%_1fr]").style(
				"border-color:var(--input-border);"
			):

				def _select_inspection(_=None, iid=insp.id) -> None:
					state.selected_inspection_id = iid
					body_area.refresh() #refresh_all()

				def _value_changed():
					state.recompute_dirty()
					header_area.refresh()

				# Inspection Name
				ui.label(insp.name).classes("min-w-0 font-medium cursor-pointer").on("click", _select_inspection)

				# App Variable
				with ui.row().classes("min-w-0 pr-6") as type_row:
					if is_row_selected:
						ui.select(
							APP_VARIABLES,
							value=insp.state_field_name if insp.state_field_name in APP_VARIABLES else None,
							on_change=lambda e, s=insp: (setattr(s, "state_field_name", e.value), _value_changed(),
													refresh_all()	),
						).props("dense").classes("w-full")
					else:
						type_row.on("click", _select_inspection).classes("cursor-pointer")
						ui.label(insp.state_field_name).classes("truncate cursor-pointer opacity-90")

				# Expected
				with ui.row().classes("min-w-0 pr-20") as expected_row:
					if is_row_selected:
						if insp.type_of_value == TYPE_LIST[0]:
							ui.select(options={True: "True", False: "False"}, value= bool(insp.expected_value),
								on_change=lambda e, s=insp: (setattr(s, "expected_value", e.value), _value_changed())
							).classes("w-full").props("dense")
						else:
							ui.input(
								value=insp.expected_value,
								on_change=lambda e, s=insp: (setattr(s, "expected_value", e.value), _value_changed()),
							).props("dense").classes("w-full")
					else:
						expected_row.on("click", _select_inspection).classes("cursor-pointer")
						ui.label(insp.expected_value).classes("truncate cursor-pointer opacity-90")

				# Type
				with ui.row().classes("min-w-0 pr-6") as type_row:
					if is_row_selected:
						ui.select(
							TYPE_LIST,
							value=insp.type_of_value,
							on_change=lambda e, s=insp: (setattr(s, "type_of_value", e.value), _value_changed(),
													refresh_all()	),
						).props("dense").classes("w-full")
					else:
						type_row.on("click", _select_inspection).classes("cursor-pointer")
						ui.label(insp.type_of_value).classes("truncate cursor-pointer opacity-90")

				# Actions
				with ui.row().classes("min-w-0 justify-end items-center gap-1 shrink-0"):

					if is_row_selected or selection_mode_active:
						icon_btn(
							"check_box" if insp.is_checked else "check_box_outline_blank",
							"Select inspection",
							lambda s=insp: inspection_toggle_one(s),
						)

					if not selection_mode_active:
						icon_btn("edit", "Rename inspection", lambda s=insp: inspection_rename(s),
								 active_color="orange")
						icon_btn("delete", "Delete inspection", lambda s=insp: inspection_delete(s),
								 active_color="negative")

	@ui.refreshable
	def body_area() -> None:
		# Body fills remaining height under header
		with ui.row().classes("w-full flex-1 overflow-hidden gap-4 p-4 rounded-b-2xl").style("background:var(--app-background);"):
			# LEFT card: Dummies
			with ui.card().classes("w-[30%] min-w-[340px] h-full overflow-hidden "
								   "rounded-2xl shadow-sm border").style("background:var(--surface); border-color:var(--input-border);"):
				# top bar stays fixed inside the card
				dummy_toolbar()
				# scroll only the list part
				with ui.scroll_area().classes("w-full h-full"):
					dummy_list_area()

			# RIGHT card: Inspections
			with ui.card().classes("flex-1 h-full overflow-hidden rounded-2xl shadow-sm border").style(
				"background:var(--surface); border-color:var(--input-border);"
			):
				inspection_toolbar()
				with ui.scroll_area().classes("w-full h-full"):
					inspection_table_area()

		# Warning overlay stays the same (optional)
		if not state.service_enabled:
			with ui.row().classes("fixed inset-0 bg-black/40 items-center justify-center z-50"):
				with ui.card().classes("w-[720px] rounded-2xl"):
					with ui.row().classes("items-center gap-4"):
						ui.icon("warning").classes("text-5xl text-orange-500")
						ui.label("Dummy service is disabled or has not been loaded!!").classes("text-2xl font-semibold")
					ui.separator()
					ui.button("Dismiss",
							  on_click=lambda: (setattr(state, "service_enabled", True), refresh_all())).props(
						"unelevated")

	@ui.refreshable
	def dummy_toolbar() -> None:
		with ui.row().classes("w-full items-center justify-between px-4 py-3 border-b").style(
			"background:var(--surface); border-color:var(--input-border);"
		):
			ui.label("Dummies").classes("text-base font-semibold")

			with ui.row().classes("items-center gap-1"):
				icon_btn("add", "Add dummy", dummy_add)

				any_sel = state.any_dummy_selected()
				all_sel = state.all_dummy_selected()
				icon = "check_box" if all_sel else ("indeterminate_check_box" if any_sel else "check_box_outline_blank")
				icon_btn(icon, "Toggle selection)", dummy_toggle_select_all)

				icon_btn(
					"delete",
					"Delete selected dummies",
					dummy_delete_selected, active_color="negative",
					enabled=state.any_dummy_selected(),
				)

	@ui.refreshable
	def inspection_toolbar() -> None:
		with ui.row().classes("w-full items-center justify-between px-4 py-3 border-b").style(
			"background:var(--surface); border-color:var(--input-border);"
		):
			ui.label("Inspections").classes("text-base font-semibold")

			with ui.row().classes("items-center gap-1"):
				icon_btn("add", "Add inspection", inspection_add, active_color="green")

				any_sel = state.any_inspection_selected()
				all_sel = state.all_inspection_selected()
				icon = "check_box" if all_sel else ("indeterminate_check_box" if any_sel else "check_box_outline_blank")
				icon_btn(icon, "Toggle selection", inspection_toggle_select_all)

				icon_btn(
					"delete",
					"Delete selected inspections",
					inspection_delete_selected, active_color="negative",
					enabled=state.any_inspection_selected(),
				)

	build_page(ctx, container, title="Config", content=build_content, show_action_bar=False)
