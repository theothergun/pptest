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
import queue
from typing import Any

from nicegui import ui
from layout.context import PageContext
from layout.page_scaffold import build_page
from pages.dummy.config_models import (DummySet, DummyTest, Inspection, TYPE_LIST,
									   DummyEditionState, CONFIG_FILE, save_config_file, load_config_file,
									   dict_to_sets, get_state_payload)
from pages.dummy.dialogs import confirm_dialog, prompt_dialog, import_dialog, create_msg_dialog, scheduler_dialog
from services.app_state import AppState
from services.worker_topics import WorkerTopics


def render(container: ui.element, ctx: PageContext) -> None:
	worker_values: dict[str, Any] = {}
	worker_sub = None
	worker_timer = None
	picker_state: dict[str, Any] = {"inspection": None, "on_select": None, "query": ""}
	picker_refs: dict[str, Any] = {"dialog": None, "title": None, "search": None}
	dialog, show_msg_dialog = create_msg_dialog()
	state = DummyEditionState()

	ui.add_head_html("""
	<style>
		.dummy-variable-trigger {
			border: 1px solid color-mix(in srgb, var(--primary) 18%, var(--input-border));
			border-radius: 14px;
			background:
				linear-gradient(135deg, color-mix(in srgb, var(--primary) 7%, var(--surface)) 0%,
				color-mix(in srgb, var(--surface-muted) 78%, transparent) 100%);
			padding: 10px 12px;
			cursor: pointer;
			transition: border-color 140ms ease, transform 140ms ease, box-shadow 140ms ease;
		}

		.dummy-variable-trigger:hover {
			border-color: color-mix(in srgb, var(--primary) 42%, var(--input-border));
			box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
			transform: translateY(-1px);
		}

		.dummy-variable-trigger.is-empty {
			background: var(--surface-muted);
			border-style: dashed;
		}

		.dummy-picker-row {
			border: 1px solid var(--tbl-row-separator);
			border-radius: 14px;
			background: color-mix(in srgb, var(--surface) 82%, var(--surface-muted));
			transition: border-color 140ms ease, transform 140ms ease, box-shadow 140ms ease;
		}

		.dummy-picker-row:hover {
			border-color: color-mix(in srgb, var(--primary) 35%, var(--tbl-row-separator));
			box-shadow: 0 12px 26px rgba(15, 23, 42, 0.08);
			transform: translateY(-1px);
		}

		.dummy-picker-row.is-selected {
			border-color: color-mix(in srgb, var(--primary) 55%, var(--tbl-row-separator));
			background: linear-gradient(135deg,
				color-mix(in srgb, var(--primary) 10%, var(--surface)) 0%,
				color-mix(in srgb, var(--tbl-row-selected) 88%, var(--surface)) 100%);
			box-shadow: 0 14px 30px rgba(15, 23, 42, 0.1);
		}
	</style>
	""")

	try:
		if ctx.worker_bus is not None:
			worker_sub = ctx.worker_bus.subscribe(WorkerTopics.VALUE_CHANGED)
	except Exception:
		worker_sub = None

	def _collect_selectable_variables() -> list[str]:
		keys = set(AppState.__annotations__.keys())

		try:
			raw_state = getattr(ctx, "state", None)
			if raw_state is not None and hasattr(raw_state, "__dict__"):
				state_map = getattr(raw_state, "__dict__", {})
				if isinstance(state_map, dict):
					for key, value in state_map.items():
						if isinstance(key, str) and key and not key.startswith("_") and not callable(value):
							keys.add(key)
		except Exception:
			pass

		keys.update(worker_values.keys())
		return sorted(keys)

	def _drain_worker_values() -> bool:
		if worker_sub is None:
			return False

		changed = False
		while True:
			try:
				msg = worker_sub.queue.get_nowait()
			except queue.Empty:
				break

			payload = getattr(msg, "payload", None) or {}
			key = str(payload.get("key") or "").strip()
			if not key:
				continue

			source = str(getattr(msg, "source", "") or "").strip()
			source_id = str(getattr(msg, "source_id", "") or "").strip()
			if not source or not source_id:
				continue

			full_key = f"{source}/{source_id}/{key}"
			value = payload.get("value")
			if worker_values.get(full_key) != value:
				changed = True
			worker_values[full_key] = value

			# Mirror worker value into app state so dummy checks can resolve this key.
			try:
				setattr(ctx.state, full_key, value)
			except Exception:
				pass

		return changed

	def _cleanup_worker_subscription() -> None:
		nonlocal worker_timer
		if worker_sub is not None:
			try:
				worker_sub.close()
			except Exception:
				pass
		if worker_timer is not None:
			try:
				worker_timer.cancel()
			except Exception:
				pass

	ui.context.client.on_disconnect(_cleanup_worker_subscription)

	def _value_for_key(key: str) -> Any:
		if not key:
			return None
		try:
			return getattr(ctx.state, key)
		except Exception:
			return None

	def _preview_value(value: Any, *, max_len: int = 90) -> str:
		if value is None:
			text = "-"
		elif isinstance(value, (dict, list, tuple)):
			try:
				text = json.dumps(value, ensure_ascii=False)
			except Exception:
				text = str(value)
		else:
			text = str(value)
		return text if len(text) <= max_len else (text[:max_len - 3] + "...")

	def _on_picker_search(value: Any) -> None:
		picker_state["query"] = str(value or "").strip().lower()
		variable_picker_rows.refresh()

	def _select_variable_from_picker(key: str) -> None:
		inspection = picker_state.get("inspection")
		on_select = picker_state.get("on_select")
		if inspection is None or on_select is None:
			return
		on_select(key)
		dlg = picker_refs.get("dialog")
		if dlg is not None:
			dlg.close()

	def _use_typed_picker_key() -> None:
		search = picker_refs.get("search")
		if search is None:
			return
		typed = str(search.value or "").strip()
		if not typed:
			ui.notify("Enter a key first", type="warning")
			return
		_select_variable_from_picker(typed)

	def _open_variable_picker(insp: Inspection, on_select) -> None:
		picker_state["inspection"] = insp
		picker_state["on_select"] = on_select
		title = picker_refs.get("title")
		if title is not None:
			title.set_text(f"Select App Variable for '{insp.name}'")
		search = picker_refs.get("search")
		if search is not None:
			search.value = insp.state_field_name or ""
		picker_state["query"] = str(insp.state_field_name or "").strip().lower()
		variable_picker_rows.refresh()
		dlg = picker_refs.get("dialog")
		if dlg is not None:
			dlg.open()

	@ui.refreshable
	def variable_picker_rows() -> None:
		keys = _collect_selectable_variables()
		query = str(picker_state.get("query") or "").strip().lower()
		current_inspection = picker_state.get("inspection")
		current_key = str(getattr(current_inspection, "state_field_name", "") or "")

		if current_key and current_key not in keys:
			keys = [current_key, *keys]

		if query:
			keys = [k for k in keys if query in k.lower()]

		if not keys:
			ui.label("No variables found").classes("px-3 py-2 text-sm opacity-70")
			return

		ui.label(f"{len(keys)} variable(s)").classes("px-1 py-2 text-xs opacity-70")
		with ui.column().classes("w-full gap-2 pb-2"):
			for key in keys:
				preview = _preview_value(_value_for_key(key))
				is_selected = (key == current_key)
				row_classes = "dummy-picker-row w-full items-center gap-4 px-4 py-3 cursor-pointer"
				if is_selected:
					row_classes += " is-selected"
				with ui.row().classes(row_classes).on("click", lambda _=None, k=key: _select_variable_from_picker(k)):
					with ui.column().classes("grow min-w-0 gap-1"):
						ui.label(key).classes("font-medium min-w-0 truncate")
						ui.label(preview).classes("text-xs opacity-75 min-w-0 truncate")
					with ui.row().classes("items-center gap-2 shrink-0"):
						if is_selected:
							ui.icon("check_circle").classes("text-[var(--primary)]")
						ui.icon("chevron_right").classes("opacity-50")


	# try to load from dummy_config.json
	try:
		if CONFIG_FILE.exists():
			load_config_file(state)
			state.selected_set = state.sets[0] if state.sets else None
			state.save_state()
	except Exception as e:
		ui.notify(f"Failed to load dummy_config.jsn: {e}", type="negative")
		print("dummy config not found")

	def build_content(_parent: ui.element) -> None:
		with ui.column().classes(f"w-full h-full overflow-hidden gap-0 rounded-2xl"
			).style("background:var(--surface-muted)"):
			header_area()
			body_area()
		with ui.dialog() as var_picker_dialog:
			with ui.card().classes("w-[1100px] max-w-[96vw] h-[82vh] rounded-[24px] overflow-hidden"):
				with ui.row().classes("w-full items-center justify-between px-1"):
					picker_refs["title"] = ui.label("Select App Variable").classes("text-lg font-semibold")
					ui.button(icon="close", on_click=var_picker_dialog.close).props("flat round")
				ui.label("Pick an existing runtime key or type one manually.").classes("text-sm opacity-70")
				picker_refs["search"] = ui.input("Search variable key").props("outlined dense clearable")
				picker_refs["search"].classes("app-input")
				picker_refs["search"].on(
					"update:model-value",
					lambda _=None: _on_picker_search(getattr(picker_refs.get("search"), "value", "")),
				)
				with ui.row().classes("w-full items-center justify-between"):
					ui.label("Matches update live from app state and worker values.").classes("text-xs opacity-60")
					ui.button("Use typed key", on_click=_use_typed_picker_key).props("outline dense no-caps")
				ui.separator()
				with ui.scroll_area().classes("w-full h-full pr-1"):
					variable_picker_rows()
		picker_refs["dialog"] = var_picker_dialog

	# -----------------------------
	# Small UI helpers
	# -----------------------------
	def icon_btn(icon: str, tooltip: str, on_click, *, enabled: bool = True,
				 active_color: str | None = None) -> ui.button:
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

		names = [s.name for s in state.sets]
		prompt_dialog("Add Set", "Set name", f"Set {next_id}", _ok, names)

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
			header_area.refresh()  # refresh_all()

		names = [s.name for s in state.sets]
		prompt_dialog("Rename Set", "Set name", state.selected_set.name, _ok, names)

	def set_save() -> None:
		# hook this to your backend save
		try:
			save_config_file(state)
			state.commit()
			refresh_all()
			ui.notify("Saved", type="positive")
			ctx.bridge.emit_patch("dummy_config_updated", True)
		except Exception as e:
			ui.notify(f"Save failed: {e}", type='negative')

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

		import_dialog(_yes, show_msg_dialog)

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
				show_msg_dialog(title, "Scheduler Settings updated (remember to Save).", mode="warning")

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

		names = [d.name for d in state.dummies]
		prompt_dialog("Add Dummy", "Dummy name", f"Dummy {next_id:03d}", _ok, names)

	def dummy_rename(dummy: DummyTest) -> None:
		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			dummy.name = name.strip()
			state.recompute_dirty()
			refresh_all()

		names = [d.name for d in state.dummies]
		prompt_dialog("Rename Dummy", "Dummy name", dummy.name, _ok, names)

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

		names = [ins.name for ins in state.inspections()]
		prompt_dialog("Add Inspection", "Inspection name", f"Inspection {next_id}", _ok, names)

	def inspection_rename(st: Inspection) -> None:
		def _ok(name: str) -> None:
			if not name.strip():
				ui.notify("Name cannot be empty", type="warning")
				return
			st.name = name.strip()
			state.recompute_dirty()
			refresh_all()

		names = [ins.name for ins in state.inspections()]
		prompt_dialog("Rename Inspection", "Inspection name", st.name, _ok, names)

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
	# ui.colors(primary="#2D3B4F")  # subtle header-ish vibe

	@ui.refreshable
	def header_area() -> None:
		with ui.row().classes("w-full items-center justify-between px-6 py-4 border-b rounded-t-2xl"
			).style("background:linear-gradient(90deg,var(--surface-muted),var(--surface)); "
					"border-color:var(--tbl-row-separator);"):

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
			).props("outlined dense").classes("w-[330px]")

			# RIGHT: Action icons
			with ui.row().classes("items-center gap-1"):
				icon_btn("add", "Add set", set_add, active_color='green')
				icon_btn("delete", "Delete set", set_delete)
				icon_btn("edit", "Rename set", set_rename, active_color='orange')

				icon_btn("save", "Save", set_save, enabled=state.has_changes,
						 active_color="negative")
				icon_btn("restore", "Discard changes", set_discard_changes, enabled=state.has_changes)

				icon_btn("file_upload", "Import", import_config)
				icon_btn("file_download", "Export", export_config, enabled=state.is_exportable())
				icon_btn("schedule", "Scheduler", scheduler_config)

				icon_btn("delete_sweep", "Delete all sets", set_delete_all,
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
				row_style = "border-color:var(--tbl-row-separator);"
				if is_selected_row:
					row_style+= " background:var(--tbl-row-selected)"
				else:
					row_cls += " row-hover"

				with ui.row().classes(row_cls).style(row_style):
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
		).style("background:var(--surface-muted); border-color:var(--tbl-row-separator);"):

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
			zebra = "" #" bg-[var(--surface)]" if i % 2 else " bg-[var(--surface-muted)]"
			hover = " hover:brightness-95"
			selected = " bg-[var(--tbl-row-selected)]" if is_row_selected else ""
			with ui.element('div').classes(base + zebra + hover + selected + " grid grid-cols-[27%_22%_22%_16%_1fr]"
				).style("border-color:var(--tbl-row-separator);"):

				def _select_inspection(_=None, iid=insp.id) -> None:
					state.selected_inspection_id = iid
					body_area.refresh()  # refresh_all()

				def _value_changed():
					state.recompute_dirty()
					header_area.refresh()

				# Inspection Name
				ui.label(insp.name).classes("min-w-0 font-medium cursor-pointer").on("click", _select_inspection)

				# App Variable
				with ui.row().classes("min-w-0 pr-6") as type_row:
					if is_row_selected:
						with ui.column().classes("w-full gap-1"):
							selected_value_preview = _preview_value(_value_for_key(insp.state_field_name))
							trigger_classes = "dummy-variable-trigger w-full"
							if not insp.state_field_name:
								trigger_classes += " is-empty"
							with ui.row().classes(trigger_classes).on(
								"click",
								lambda _=None, s=insp: _open_variable_picker(
									s,
									lambda key, ins=s: (
										setattr(ins, "state_field_name", key),
										_value_changed(),
										refresh_all(),
									),
								),
							):
								with ui.column().classes("grow min-w-0 gap-[2px]"):
									ui.label(insp.state_field_name or "Choose a runtime variable").classes(
										"font-medium min-w-0 truncate"
									)
									ui.label(f"Current value: {selected_value_preview}").classes(
										"text-xs opacity-75 min-w-0 truncate"
									)
								ui.icon("search").classes("text-[18px] opacity-65")
					else:
						type_row.on("click", _select_inspection).classes("cursor-pointer")
						ui.label(insp.state_field_name).classes("truncate cursor-pointer opacity-90")

				# Expected
				with ui.row().classes("min-w-0 pr-20") as expected_row:
					if is_row_selected:
						if insp.type_of_value == TYPE_LIST[0]:
							ui.select(options={True: "True", False: "False"}, value=bool(insp.expected_value),
									  on_change=lambda e, s=insp: (setattr(s, "expected_value", e.value),
																   _value_changed())
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
														 refresh_all()),
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
		with ui.row().classes("w-full flex-1 overflow-hidden gap-4 p-4 rounded-b-2xl"
			).style("background:var(--surface-muted);"):
			# LEFT card: Dummies
			with ui.card().classes("w-[30%] min-w-[340px] h-full overflow-hidden "
				   "rounded-2xl border").style("background:var(--surface); border-color:var(--tbl-row-separator);"):
				# top bar stays fixed inside the card
				dummy_toolbar()
				# scroll only the list part
				with ui.scroll_area().classes("w-full h-full"):
					dummy_list_area()

			# RIGHT card: Inspections
			with ui.card().classes("flex-1 h-full overflow-hidden rounded-2xl border").style(
				"background:var(--surface); border-color:var(--tbl-row-separator);"
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
			"border-color:var(--input-border);"
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
			"border-color:var(--input-border);"
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

	worker_timer = ui.timer(
		0.25,
		lambda: (
			inspection_table_area.refresh(),
			variable_picker_rows.refresh(),
		) if _drain_worker_values() else None
	)

	build_page(ctx, container, title="Config", content=build_content, show_action_bar=False)
