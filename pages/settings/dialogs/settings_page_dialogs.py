from __future__ import annotations

from typing import Callable

from nicegui import ui

from services.app_config import (
	list_config_sets,
	get_active_set_name,
	create_config_set,
	delete_config_set,
)


def open_create_set_dialog(*, on_done: Callable | None = None) -> None:
	"""
	Opens a dialog to create a new config set.
	on_done: optional callback called after successful creation (e.g., refresh selector).
	"""
	d = ui.dialog()
	with d:
		with ui.card().classes("w-[min(520px,95vw)] gap-3 p-0 overflow-hidden"):
			with ui.row().classes("w-full h-10 items-center px-4 bg-primary text-white"):
				ui.label("Create config set").classes("text-lg font-semibold")

			with ui.column().classes("w-full p-4 gap-4"):
				name_in = ui.input("Set name").classes("w-full")
				template_sel = ui.select(
					list_config_sets(),
					label="Copy from (optional)",
				).classes("w-full")

				def create() -> None:
					try:
						name = create_config_set(name_in.value, copy_from=template_sel.value)
						ui.notify(f"Created: {name}", type="positive")
						d.close()
						if on_done:
							on_done()
					except Exception as ex:
						ui.notify(str(ex), type="negative")

				with ui.row().classes("w-full justify-end gap-2"):
					ui.button("Cancel", on_click=d.close).props("flat")
					ui.button("Create", on_click=create).props("color=primary")
	d.open()


def open_delete_set_dialog(
	*,
	selected_set: str | None,
	on_done: Callable | None = None,
) -> None:
	"""
	Opens a confirmation dialog to delete a config set.
	selected_set: current selected value from the selector
	on_done: optional callback called after successful deletion (e.g., refresh selector).
	"""
	name = (selected_set or get_active_set_name()).strip()

	if name == "default":
		ui.notify("The 'default' set cannot be deleted.", type="warning")
		return

	d = ui.dialog()
	with d:
		with ui.card().classes("w-[min(520px,95vw)] gap-3  p-0 overflow-hidden"):
			with ui.row().classes("w-full h-10 items-center px-4 bg-negative text-white"):
				ui.label("Delete config set").classes("text-lg font-semibold")
			with ui.column().classes("w-full p-4 gap-4"):
				ui.label(
					f"Are you sure you want to delete '{name}'? This cannot be undone."
				).classes("text-sm text-gray-600")

				def confirm_delete() -> None:
					try:
						delete_config_set(name)
						ui.notify(f"Deleted config set: {name}", type="positive")
						d.close()
						if on_done:
							on_done()
					except Exception as ex:
						ui.notify(str(ex), type="negative")

				with ui.row().classes("w-full justify-end gap-2"):
					ui.button("Cancel", on_click=d.close).props("flat")
					ui.button("Delete", on_click=confirm_delete).props("color=negative")

	d.open()
