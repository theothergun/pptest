from __future__ import annotations

from nicegui import ui

from layout.main_area import PageContext
from pages.settings.route import route_settings
from pages.settings.tcp_client import tcp_settings
from pages.settings.rest_api import rest_api_settings
from pages.settings import scripts_lab
from pages.settings import language_manager

from services.app_config import (
	list_config_sets,
	get_active_set_name,
	create_config_set,
	set_active_set,
)
from services.i18n import t


def render(container: ui.element, ctx: PageContext) -> None:
	with container:

		# -------------------------------
		# HEADER ROW
		# -------------------------------
		with ui.row().classes("w-full items-center justify-between"):

			# Left side (title + subtitle)
			with ui.column().classes("gap-0"):
				ui.label(t("settings.title", "Settings")).classes("text-2xl font-bold")
				ui.label(
					t("settings.subtitle", "Manage application settings and worker configuration.")
				).classes("text-sm text-gray-500")

			# Right side (config set selector)
			with ui.row().classes("items-center gap-2"):

				def refresh_sets():
					selector.options = list_config_sets()
					selector.value = get_active_set_name()

				def on_change(e):
					set_active_set(e.value)
					ui.notify(f"Active config set: {e.value}", type="positive")
					ui.run_javascript("location.reload()")

				def open_create_dialog():
					d = ui.dialog()
					with d:
						with ui.card().classes("w-[min(480px,95vw)] gap-3"):
							ui.label("Create config set").classes("text-lg font-semibold")

							name_in = ui.input("Set name").classes("w-full")
							template_sel = ui.select(
								list_config_sets(),
								label="Copy from (optional)"
							).classes("w-full")

							def create():
								try:
									name = create_config_set(
										name_in.value,
										copy_from=template_sel.value,
									)
									ui.notify(f"Created: {name}", type="positive")
									refresh_sets()
									d.close()
								except Exception as ex:
									ui.notify(str(ex), type="negative")

							with ui.row().classes("justify-end gap-2"):
								ui.button("Cancel", on_click=d.close).props("flat")
								ui.button("Create", on_click=create).props("color=primary")
					d.open()

				ui.label("Config:").classes("text-sm text-gray-500")

				selector = ui.select(
					options=list_config_sets(),
					value=get_active_set_name(),
					on_change=on_change,
				).props("dense outlined").classes("min-w-[160px]")

				ui.button(icon="add", on_click=open_create_dialog)\
					.props("dense flat round")

		ui.separator().classes("my-3")

		# -------------------------------
		# TABS
		# -------------------------------
		with ui.tabs().classes("w-full") as tabs:
			ui.tab("Routes")
			ui.tab("TCP Clients")
			ui.tab("Scripts")
			ui.tab("REST APIs")
			ui.tab("Languages")

		with ui.tab_panels(tabs, value="Routes").classes("w-full"):
			with ui.tab_panel("Routes"):
				route_settings.render(ui.column().classes("w-full gap-4"), ctx)
			with ui.tab_panel("TCP Clients"):
				tcp_settings.render(ui.column().classes("w-full gap-4"), ctx)
			with ui.tab_panel("Scripts"):
				scripts_lab.render(ui.column().classes("w-full gap-4"), ctx)
			with ui.tab_panel("REST APIs"):
				rest_api_settings.render(ui.column().classes("w-full gap-4"), ctx)
			with ui.tab_panel("Languages"):
				language_manager.render(ui.column().classes("w-full gap-4"), ctx)
