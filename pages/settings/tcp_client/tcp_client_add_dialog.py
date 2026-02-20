from __future__ import annotations

from typing import Callable
from nicegui import ui


def create_add_tcp_client_dialog(
	*,
	on_add: Callable[[dict], bool],
) -> tuple[ui.dialog, Callable[[], None]]:
	dialog = ui.dialog()

	with dialog:
		with ui.card().classes("w-[min(860px,95vw)] p-0 overflow-hidden"):
			# header
			with ui.row().classes("w-full h-10 items-center px-4 bg-primary text-white"):
				ui.label("Add TCP client").classes("text-base font-semibold")

			# body
			with ui.column().classes("w-full p-4 gap-4"):
				client_id = ui.input("Client ID").classes("w-full")
				with ui.row().classes("w-full gap-3"):
					host = ui.input("Host").classes("flex-1")
					port = ui.input("Port").classes("w-40")

				with ui.row().classes("w-full items-center gap-6"):
					connect = ui.switch("Connect on startup", value=True).classes("flex-1")
					auto_reconnect = ui.switch("Auto reconnect", value=True).classes("flex-1")

				with ui.row().classes("w-full items-center gap-6"):
					keepalive = ui.switch("Keepalive", value=True).classes("flex-1")
					tcp_no_delay = ui.switch("TCP no delay", value=True).classes("flex-1")
				visible_on_device_panel = ui.switch("Visible on device panel", value=False).classes("w-full")

				mode = ui.input("Mode", value="line").classes("w-full")
				delimiter = ui.input("Delimiter", value="\\n").classes("w-full")
				encoding = ui.input("Encoding", value="utf-8").classes("w-full")

				with ui.row().classes("w-full gap-3"):
					reconnect_min_s = ui.input("Reconnect min (s)", value="1.0").classes("flex-1")
					reconnect_max_s = ui.input("Reconnect max (s)", value="10.0").classes("flex-1")

				def clear() -> None:
					client_id.value = ""
					host.value = ""
					port.value = ""
					connect.value = True
					mode.value = "line"
					delimiter.value = "\\n"
					encoding.value = "utf-8"
					auto_reconnect.value = True
					reconnect_min_s.value = "1.0"
					reconnect_max_s.value = "10.0"
					keepalive.value = True
					tcp_no_delay.value = True
					visible_on_device_panel.value = False

				def handle_add() -> None:
					payload = {
						"client_id": client_id.value,
						"host": host.value,
						"port": port.value,
						"connect": connect.value,
						"mode": mode.value,
						"delimiter": delimiter.value,
						"encoding": encoding.value,
						"auto_reconnect": auto_reconnect.value,
						"reconnect_min_s": reconnect_min_s.value,
						"reconnect_max_s": reconnect_max_s.value,
						"keepalive": keepalive.value,
						"tcp_nodelay": tcp_no_delay.value,
						"visible_on_device_panel": visible_on_device_panel.value,
					}
					ok = on_add(payload)
					if not ok:
						return
					clear()
					dialog.close()

				with ui.row().classes("w-full justify-end gap-2"):
					ui.button("Cancel", on_click=dialog.close).props("flat")
					ui.button("Add client", on_click=handle_add).props("color=primary")

	def open_dialog() -> None:
		dialog.open()

	return dialog, open_dialog
