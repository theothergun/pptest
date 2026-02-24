import asyncio
import json
import copy

from nicegui import ui
from nicegui.events import UploadEventArguments


def confirm_dialog(title: str, message: str, on_yes,*, mode = "error") -> None:
	colors = {"info": "bg-primary", "warning": "bg-orange", "success": "bg-green", "error": "bg-negative"}
	bg_class = colors.get(mode, "primary")
	with ui.dialog() as d, ui.card().classes("w-[480px] p-0").style(
		"background:var(--surface); color:var(--text-primary); border:1px solid var(--input-border);"
	):
		with ui.row().classes(f"w-full p-2 {bg_class}"):
			ui.label(title).classes("text-lg font-semibold text-white")
		with ui.column().classes("w-full px-4"):
			ui.label(message).classes("text-sm opacity-80")
			with ui.row().classes("w-full items-center justify-end gap-2 py-2"):
				ui.button("Cancel", on_click=d.close).props("flat")
				ui.button("Yes", on_click=lambda: (d.close(), on_yes())).props("flat").classes(f"{bg_class} text-white")
	d.open()


def create_msg_dialog():
	colors = {"info": "bg-primary", "warning": "bg-orange", "success": "bg-green", "error": "bg-negative"}
	with ui.dialog() as d, ui.card().classes("w-[480px] p-0").style(
		"background:var(--surface); color:var(--text-primary); border:1px solid var(--input-border);"
	):
		with ui.row().classes(f"w-full p-2 bg-primary") as header:
			title_lbl = ui.label("").classes("text-lg font-semibold text-white")
		with ui.column().classes("w-full px-4"):
			msg_lbl = ui.label("").classes("text-sm opacity-80")
			with ui.row().classes("w-full items-center justify-end gap-2 py-2"):
				ok_btn = ui.button("Ok", on_click=lambda: d.close()).props("flat").classes("bg-primary text-white")

	def show(title: str, message: str,*, mode = "error"):
		bg = colors.get(mode, "bg-primary")
		title_lbl.text = title
		msg_lbl.text = message
		#reset header/button bg classes
		header.classes(remove=" ".join(value for key, value in colors.items()))
		header.classes(add=bg)
		ok_btn.classes(remove=" ".join(value for key, value in colors.items()))
		ok_btn.classes(add=bg)
		d.open()

	return d, show


def prompt_dialog(title: str, label: str, initial: str, on_ok, ok_label = "Save", cancel_label ="Cancel") -> None:
	with ui.dialog() as d, ui.card().classes("w-[520px] p-0").style(
		"background:var(--surface); color:var(--text-primary); border:1px solid var(--input-border);"
	):
		with ui.row().classes("w-full bg-primary text-white p-2"):
			ui.label(title).classes("text-lg font-semibold")
		with ui.column().classes("w-full p-2"):
			inp = ui.input(label=label, value=initial).props("outlined dense").classes("w-full")
			with ui.row().classes("w-full justify-end gap-2 pt-2"):
				ui.button(cancel_label, on_click=d.close).props("flat")
				ui.button(ok_label, on_click=lambda: (d.close(), on_ok(inp.value)))\
					.props("unelevated").classes("bg-primary text-white")
	d.open()


def import_dialog(on_ok, show_msg_dialog) -> None:
	with ui.dialog() as dlg, ui.card().classes("w-[560px] p-0").style(
		"background:var(--surface); color:var(--text-primary); border:1px solid var(--input-border);"
	):
		with ui.row().classes("w-full bg-primary text-white p-2"):
			title = ui.label("Import Dummy Config").classes("text-lg font-semibold")
		with ui.column().classes("w-full p-2"):
			ui.label("Upload a JSON file (exported or compatible format).").classes("text-sm opacity-70")
			async def on_upload(e: UploadEventArguments) -> None:
				file_obj = getattr(e, "content", None) or getattr(e, "file", None)
				try:
					data_byte = await file_obj.read()
					raw = data_byte.decode("utf-8")
					data = json.loads(raw)
					on_ok(data)
					dlg.close()
					show_msg_dialog(title.text,"Config imported (remember to Save).",mode="warning")
				except Exception as ex:
					show_msg_dialog(title.text,f"Import failed: {ex}", mode="error")

			ui.upload(on_upload=on_upload).props("accept=.json").classes("w-full")
			with ui.row().classes("w-full justify-end pt-2"):
				ui.button("Close", on_click=dlg.close).props("flat")

	dlg.open()


INTERVAL_UNITS = {"minute":"Minute(s)", "hour":"Hour(s)", "day":"Day(s)"}
CLEAN_UNITS = {"day":"Day(s)", "week":"Week(s)", "month":"Month(s)", "year":"Year(s)"}

def scheduler_dialog(settings, on_ok) -> None:
	draft = copy.deepcopy(settings)

	def block_classes(disabled: bool) -> str:
		base = "w-full rounded-xl border shadow-sm p-0"
		return base + (" opacity-50 pointer-events-none" if disabled else "")

	with ui.dialog() as dlg:
		with ui.card().classes("w-[680px] max-w-[92vw] p-0 rounded-2xl overflow-hidden").style(
			"background:var(--surface); color:var(--text-primary); border:1px solid var(--input-border);"
		):
			# Header (more compact)
			with ui.row().classes("w-full items-center justify-between px-3 py-1 bg-primary text-white"):
				with ui.row().classes("items-center gap-2"):
					ui.icon("schedule").classes("text-lg")
					ui.label("Dummy Execution Configuration").classes("text-base font-semibold")
				ui.button(icon="close", on_click=dlg.close).props("flat round dense").classes("text-white")

			with ui.column().classes("w-full p-3 gap-2").style("background:var(--surface); color:var(--text-primary);"):

				# --- Activation ---
				with ui.card().classes("w-full rounded-xl border shadow-sm p-0").style("border-color:var(--input-border); background:var(--surface);"):
					with ui.row().classes("w-full items-center justify-between px-2 py-1.5 border-b").style(
						"border-color:var(--input-border); background:var(--surface-muted);"
					):
						ui.label("Activate / Deactivate the Dummy check").classes("font-semibold text-[14px]")

						@ui.refreshable
						def activation_status() -> None:
							ui.label("ON" if draft.is_dummy_activated else "OFF") \
								.classes("text-[12px] font-semibold") \
								.style(f"color: {'var(--positive)' if draft.is_dummy_activated else 'var(--text-secondary)'}")

						def on_active_change(e):
							setattr(draft, "is_dummy_activated", e.value)
							activation_status.refresh()
							execution_block.refresh()
							mode_block.refresh()
							cleanup_block.refresh()

						with ui.row().classes("items-center gap 2"):
							ui.switch(value=draft.is_dummy_activated, on_change=on_active_change).props("color=positive dense")
							activation_status()

					with ui.row().classes("w-full items-center justify-between px-2 pb-2 py-1.5"):
						ui.label("Dummy Check").classes("text-[12px] opacity-80")

				# --- Execution ---
				@ui.refreshable
				def execution_block() -> None:
					disabled = not draft.is_dummy_activated

					with ui.card().classes(block_classes(disabled)):
						with ui.row().classes("w-full items-center justify-between px-2 py-1.5 border-b").style(
							"border-color:var(--input-border); background:var(--surface-muted);"
						):
							ui.label("When to execute").classes("font-semibold text-[14px]")

						with ui.column().classes("w-full gap-2"):
							@ui.refreshable
							def interval_block() -> None:
								if not draft.on_interval:
									return
								with ui.row().classes("items-center gap-2"):
									ui.label("Every").classes("text-[12px] font-semibold opacity-80")

									n = ui.number(
										value=draft.interval_value,
										min=1,
										step=1,
										on_change=lambda e: setattr(draft, "interval_value", int(e.value or 1)),
									).props("dense").classes("w-20 pb-2")
									n.props("inputmode=numeric")

									u = ui.select(
										options=INTERVAL_UNITS,
										value=draft.interval_unit,
										on_change=lambda e: setattr(draft, "interval_unit", e.value),
									).props("dense").classes("w-36 pb-2")

									if disabled:
										n.disable()
										u.disable()

							def toggle_row(label: str, attr: str):
								with ui.row().classes("w-full min-h-[40px] items-center justify-between"):
									ui.label(label).classes("text-[12px]")
									if attr == "on_interval":
										interval_block()
									sw = ui.switch(
										value=getattr(draft, attr),
										on_change=lambda e, a=attr: (setattr(draft, a, e.value), interval_block.refresh()),
									).props("color=primary dense")
									if disabled:
										sw.disable()

							toggle_row("On Machine Start", "on_machine_start")
							toggle_row("On Program Change", "on_program_change")
							toggle_row("On Interval", "on_interval")



				execution_block()

				# --- Mode ---
				@ui.refreshable
				def mode_block() -> None:
					disabled = not draft.is_dummy_activated

					with ui.card().classes(block_classes(disabled)):
						with ui.row().classes("w-full items-center justify-between px-2 py-1.5 border-b").style(
							"border-color:var(--input-border); background:var(--surface-muted);"
						):
							ui.label("Execution mode").classes("font-semibold text-[14px]")

						with ui.row().classes("w-full items-center justify-between px-2 py-2"):
							ui.label("Dummy Identification Execution").classes("text-[12px] opacity-80")

							with ui.row().classes("items-center gap-2"):
								def on_mode_change(e):
									setattr(draft, "is_predetermined", e.value)
									mode_status.refresh()

								sw = ui.switch(
									value=draft.is_predetermined,
									on_change=on_mode_change,
								).props("color=primary dense")

								if disabled:
									sw.disable()

								@ui.refreshable
								def mode_status():
									ui.label("ON" if draft.is_predetermined else "OFF") \
										.classes("text-[12px] font-semibold") \
										.style(f"color: {'var(--primary)' if draft.is_predetermined else 'var(--text-secondary)'}")

								mode_status()

				mode_block()

				# --- Cleanup ---
				@ui.refreshable
				def cleanup_block() -> None:
					disabled = not draft.is_dummy_activated

					with ui.card().classes(block_classes(disabled)):
						with ui.row().classes("w-full items-center justify-between px-2 py-1.5 border-b").style(
							"border-color:var(--input-border); background:var(--surface-muted);"
						):
							ui.label("History cleanup").classes("font-semibold text-[14px]")

							def on_cleanup_change(e):
								setattr(draft, "clean_enabled", e.value)
								cleanup_status.refresh()
								clean_details.refresh()

							with ui.row().classes("items-center gap-2"):
								sw = ui.switch(
									value=draft.clean_enabled,
									on_change=on_cleanup_change,
								).props("color=warning dense")

								if disabled:
									sw.disable()

								@ui.refreshable
								def cleanup_status():
									ui.label("ON" if draft.clean_enabled else "OFF") \
										.classes("text-[12px] font-semibold") \
										.style(f"color: {'var(--warning)' if draft.clean_enabled else 'var(--text-secondary)'}")

								cleanup_status()

						with ui.row().classes("w-full items-center justify-between px-2 py-2 min-h-[40px]"):
							ui.label("Clean entries").classes("text-[12px] opacity-80")
							@ui.refreshable
							def clean_details() -> None:
								if not draft.clean_enabled:
									return

								with ui.row().classes("items-center gap-2"):
									ui.label("Older than").classes("text-[12px] font-semibold opacity-80 min-w-[70px]")

									n = ui.number(
										value=draft.clean_older_value,
										min=1,
										step=1,
										on_change=lambda e: setattr(draft, "clean_older_value", int(e.value or 1)),
									).props("dense").classes("w-20 pb-2")
									n.props("inputmode=numeric")

									u = ui.select(
										options=CLEAN_UNITS,
										value=draft.clean_older_unit,
										on_change=lambda e: setattr(draft, "clean_older_unit", e.value),
									).props("dense").classes("w-36 pb-2")

									if disabled:
										n.disable()
										u.disable()

							clean_details()
							ui.element("div").style("width: 10px;")


				cleanup_block()

			# Footer (compact)
			with ui.row().classes("w-full items-center justify-end gap-2 px-3 py-2 border-t").style(
				"background:var(--surface-muted); border-color:var(--input-border);"
			):
				ui.button("Cancel", on_click=dlg.close).props("flat dense")
				ui.button("Ok", on_click=lambda: (on_ok(draft), dlg.close())).props("unelevated").classes("bg-primary text-white")

	dlg.open()
