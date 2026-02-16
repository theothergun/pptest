from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from services.app_config import get_app_config, save_app_config
from services.app_lifecycle import request_app_restart


def render(container: ui.element, _ctx: PageContext) -> None:
	with container.classes("w-full"):
		cfg = get_app_config()
		current = bool(getattr(cfg.ui.navigation, "hide_nav_on_startup", False))

		with ui.card().classes("w-full"):
			ui.label("General Settings").classes("text-xl font-semibold")
			ui.label("General UI behavior settings.").classes("text-sm text-gray-500")

			hide_nav_switch = ui.switch("Hide nav on startup", value=current)

			def save_settings() -> None:
				cfg = get_app_config()
				cfg.ui.navigation.hide_nav_on_startup = bool(hide_nav_switch.value)
				save_app_config(cfg)
				ui.notify("General settings saved.", type="positive")

			def open_restart_dialog() -> None:
				d = ui.dialog()
				with d, ui.card().classes("w-[520px] max-w-[95vw]"):
					ui.label("Restart application?").classes("text-lg font-semibold")
					ui.label("This will disconnect all active sessions and restart the backend process.").classes("text-sm text-gray-600")
					with ui.row().classes("w-full justify-end gap-2"):
						ui.button("Cancel", on_click=d.close).props("flat")

						def confirm_restart() -> None:
							d.close()
							ui.notify("Restarting application...", type="warning")
							request_app_restart(delay_s=1.0)

						ui.button("Restart now", on_click=confirm_restart).props("color=negative")
				d.open()

			with ui.row().classes("w-full justify-end gap-2"):
				ui.button("Restart Application", on_click=open_restart_dialog).props("outline color=negative")
				ui.button("Save", on_click=save_settings).props("color=primary")
