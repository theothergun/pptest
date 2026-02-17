from __future__ import annotations

from nicegui import ui

from layout.main_area import PageContext
from pages.settings.settings_layout import render_settings_header
from pages.settings import general_settings
from pages.settings import theme_settings
from pages.settings import startup_settings
from pages.settings import app_state_view
from pages.settings import online_status
from pages.settings import enabled_workers_settings
from pages.settings import scripts_lab
from pages.settings.route import route_settings
from pages.settings.tcp_client import tcp_settings
from pages.settings import twincat_settings
from pages.settings import itac_settings
from pages.settings import com_device_settings
from pages.settings import opcua_settings
from pages.settings import rest_api_settings
from pages.settings import language_manager
from services.i18n import t


def render(container: ui.element, ctx: PageContext) -> None:
	with container:
		with ui.column().classes("w-full h-full min-h-0"):
			render_settings_header(
				ctx,
				title=t("settings.title", "Settings"),
				subtitle=t("settings.subtitle", "Manage application settings and worker configuration."),
			)
			with ui.column().classes("w-full flex-1 min-h-0"):
				ui.label(t("settings.sections", "Sections")).classes("text-sm text-gray-500 mt-2")

				with ui.row().classes("w-full flex-1 min-h-0 overflow-hidden gap-4"):
					left_col = ui.column().classes("w-[260px] min-w-[220px] max-w-[320px] h-full min-h-0 overflow-y-auto")

					nodes = [
						{
							"id": "general",
							"label": t("settings.general.title", "General"),
							"icon": "tune",
							"children": [
								{"id": "general.core", "label": t("settings.general.core", "General Settings"), "icon": "settings"},
								{"id": "general.themes", "label": t("settings.general.themes", "Color Themes"), "icon": "palette"},
								{"id": "general.startup", "label": t("settings.general.startup", "Startup"), "icon": "rocket_launch"},
							],
						},
						{
							"id": "runtime",
							"label": t("settings.runtime.title", "Runtime"),
							"icon": "monitor_heart",
							"children": [
								{"id": "runtime.app_state", "label": t("settings.runtime.app_state", "Application Variables"), "icon": "data_object"},
								{"id": "runtime.online", "label": t("settings.runtime.online", "Online Status"), "icon": "cloud_done"},
							],
						},
						{
							"id": "workers",
							"label": t("settings.workers.title", "Workers"),
							"icon": "engineering",
							"children": [
								{"id": "workers.enabled", "label": t("settings.workers.enabled", "Enabled Workers"), "icon": "toggle_on"},
								{"id": "workers.scripts", "label": t("settings.workers.scripts", "Scripts"), "icon": "terminal"},
							],
						},
						{
							"id": "connectivity",
							"label": t("settings.connectivity.title", "Connectivity"),
							"icon": "hub",
							"children": [
								{"id": "connectivity.routes", "label": t("settings.connectivity.routes", "Routes"), "icon": "route"},
								{"id": "connectivity.tcp", "label": t("settings.connectivity.tcp", "TCP Clients"), "icon": "swap_horiz"},
								{"id": "connectivity.twincat", "label": t("settings.connectivity.twincat", "TwinCAT"), "icon": "memory"},
								{"id": "connectivity.itac", "label": t("settings.connectivity.itac", "iTAC"), "icon": "factory"},
								{"id": "connectivity.com", "label": t("settings.connectivity.com", "COM Device"), "icon": "usb"},
								{"id": "connectivity.opcua", "label": t("settings.connectivity.opcua", "OPC UA"), "icon": "device_hub"},
								{"id": "connectivity.rest", "label": t("settings.connectivity.rest", "REST APIs"), "icon": "cloud"},
							],
						},
						{
							"id": "languages",
							"label": t("settings.languages.title", "Languages"),
							"icon": "language",
							"children": [
								{"id": "languages.manager", "label": t("settings.languages.manager", "Language Manager"), "icon": "translate"},
							],
						},
					]

					leaf_ids: set[str] = set()

					def _collect_leaf_ids(items: list[dict]) -> None:
						for n in items:
							children = n.get("children")
							if children:
								_collect_leaf_ids(children)
							else:
								leaf_ids.add(n.get("id"))

					_collect_leaf_ids(nodes)

					# Content area
					content = ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-4")

					def render_panel(panel_id: str) -> None:
						content.clear()
						with content:
							if panel_id == "general.core":
								general_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "general.themes":
								theme_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "general.startup":
								startup_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "runtime.app_state":
								app_state_view.render(ui.column().classes("w-full h-full min-h-0"), ctx)
							elif panel_id == "runtime.online":
								online_status.render(ui.column().classes("w-full h-full min-h-0"), ctx)
							elif panel_id == "workers.enabled":
								enabled_workers_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "workers.scripts":
								scripts_lab.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.routes":
								route_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.tcp":
								tcp_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.twincat":
								twincat_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.itac":
								itac_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.com":
								com_device_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.opcua":
								opcua_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "connectivity.rest":
								rest_api_settings.render(ui.column().classes("w-full gap-4"), ctx)
							elif panel_id == "languages.manager":
								language_manager.render(ui.column().classes("w-full gap-4"), ctx)
							else:
								ui.label(t("settings.select_hint", "Select a section from the tree.")).classes("text-sm text-gray-500")

					def on_select(e) -> None:
						node_id = getattr(e, "value", None)
						if node_id in leaf_ids:
							render_panel(node_id)

					with left_col:
						nav_tree = ui.tree(nodes, label_key="label", on_select=on_select).classes("w-full")
						nav_tree.props("dense")

					# default view
					render_panel("general.core")
