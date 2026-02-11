from __future__ import annotations

from typing import Callable
from nicegui import ui


def create_add_route_dialog(
	*,
	on_add: Callable[[str, str, str, str, str, bool], bool],
) -> tuple[ui.dialog, Callable[[], None]]:
	"""
	Builds the 'Add route' dialog.

	on_add: callback that performs the add and returns True on success
	returns: (dialog, open_dialog)
	"""

	dialog = ui.dialog()

	with dialog:
		with ui.card().classes("w-[min(720px,95vw)] gap-4 p-0"):
			#header
			with ui.row().classes("w-full h-10 items-center px-4 bg-primary text-white"):
				ui.label("Add route").classes("text-base font-semibold")

			with ui.column().classes("w-full p-4 gap-4"):
				key_input = ui.input("Route key (e.g. packaging)").classes("w-full")
				label_input = ui.input("Label").classes("w-full")
				icon_input = ui.input("Icon (material icon name)").classes("w-full").props("placeholder=settings")
				path_input = ui.input("File path (e.g. packaging/packaging.py)").classes("w-full")
				roles_input = ui.input("Allowed roles (comma separated)").classes("w-full")

				def clear_inputs() -> None:
					key_input.value = ""
					label_input.value = ""
					icon_input.value = ""
					path_input.value = ""
					roles_input.value = ""
					set_as_main_route.value = False

				def handle_add() -> None:
					ok = on_add(
						key_input.value,
						label_input.value,
						icon_input.value,
						path_input.value,
						roles_input.value,
						bool(set_as_main_route.value)
					)
					if not ok:
						return
					clear_inputs()
					dialog.close()

				with ui.row().classes("w-full justify-end gap-2"):
					set_as_main_route = ui.switch("Set as main route", value=False)
					ui.button("Cancel", on_click=dialog.close).props("flat")
					ui.button("Add route", on_click=handle_add).props("color=primary")

	def open_dialog() -> None:
		dialog.open()


	return dialog, open_dialog
