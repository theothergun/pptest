from __future__ import annotations

from nicegui import ui

from layout.main_area import PageContext
from pages.settings.settings_layout import render_settings_header
from pages.settings import general_settings
from pages.settings import theme_settings
from pages.settings import startup_settings
from pages.settings import user_management
from pages.settings import global_variables_settings
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
	# IMPORTANT:
	# The page scaffold usually wraps `container` in an overflow-auto scroll area.
	# For Settings we want scrolling INSIDE the settings panels, not on the outer scaffold.
	# Inline style with !important wins over the scaffold's classes.
	container.style("overflow: hidden !important;")
	container.style("min-height: 0 !important;")

	with container:
		with ui.column().classes("w-full h-full min-h-0 min-w-0"):
			render_settings_header(
				ctx,
				title=t("settings.title", "Settings"),
				subtitle=t("settings.subtitle", "Manage application settings and worker configuration."),
			)

			# Body must be flex-1 + min-h-0 so inner scroll containers can work
			with ui.column().classes("w-full flex-1 min-h-0 min-w-0"):
				ui.label(t("settings.sections", "Sections")).classes("text-sm text-gray-500 mt-2")

				# Keep a strict 2-column split; wrapping here can clip the right panel.
				with ui.row().classes("w-full flex-1 min-h-0 min-w-0 overflow-hidden gap-4 no-wrap items-stretch"):
					# Left navigation scroll
					left_col = ui.column().classes("w-[260px] min-w-[220px] max-w-[320px] h-full min-h-0 overflow-y-auto shrink-0")
					left_col.style("overscroll-behavior: contain;")

					nodes = [
						{
							"id": "general",
							"label": f"⚙️ {t('settings.general.title', 'General')}",
							"children": [
								{"id": "general.core", "label": f"🛠️ {t('settings.general.core', 'General Settings')}"},
								{"id": "general.themes", "label": f"🎨 {t('settings.general.themes', 'Color Themes')}"},
								{"id": "general.startup", "label": f"🚀 {t('settings.general.startup', 'Startup')}"},
								{"id": "general.users", "label": f"👤 {t('settings.general.users', 'User Management')}"},
								{"id": "general.global_vars", "label": f"🌐 {t('settings.general.global_vars', 'Global Variables')}"},
							],
						},
						{
							"id": "runtime",
							"label": f"🧠 {t('settings.runtime.title', 'Runtime')}",
							"children": [
								{"id": "runtime.app_state", "label": f"📦 {t('settings.runtime.app_state', 'Application Variables')}"},
								{"id": "runtime.online", "label": f"☁️ {t('settings.runtime.online', 'Online Status')}"},
							],
						},
						{
							"id": "workers",
							"label": f"👷 {t('settings.workers.title', 'Workers')}",
							"children": [
								{"id": "workers.enabled", "label": f"✅ {t('settings.workers.enabled', 'Enabled Workers')}"},
								{"id": "workers.scripts", "label": f"💻 {t('settings.workers.scripts', 'Scripts')}"},
							],
						},
						{
							"id": "connectivity",
							"label": f"🔌 {t('settings.connectivity.title', 'Connectivity')}",
							"children": [
								{"id": "connectivity.routes", "label": f"🧭 {t('settings.connectivity.routes', 'Routes')}"},
								{"id": "connectivity.tcp", "label": f"🛰️ {t('settings.connectivity.tcp', 'TCP Clients')}"},
								{"id": "connectivity.twincat", "label": f"🧩 {t('settings.connectivity.twincat', 'TwinCAT')}"},
								{"id": "connectivity.itac", "label": f"🏭 {t('settings.connectivity.itac', 'iTAC')}"},
								{"id": "connectivity.com", "label": f"🔗 {t('settings.connectivity.com', 'COM Device')}"},
								{"id": "connectivity.opcua", "label": f"📡 {t('settings.connectivity.opcua', 'OPC UA')}"},
								{"id": "connectivity.rest", "label": f"🌐 {t('settings.connectivity.rest', 'REST APIs')}"},
							],
						},
						{
							"id": "languages",
							"label": f"🌍 {t('settings.languages.title', 'Languages')}",
							"children": [
								{"id": "languages.manager", "label": f"🗣️ {t('settings.languages.manager', 'Language Manager')}"},
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

					# Right side: ALWAYS the scroll container for settings pages
					right_col = ui.column().classes("flex-1 h-full min-h-0 min-w-0 overflow-hidden")

					def render_panel(panel_id: str) -> None:
						right_col.clear()

						with right_col:
							# This is the only scroll container on the right side.
							panel_scroll = ui.column().classes("w-full h-full flex-1 min-h-0 min-w-0 overflow-y-auto overflow-x-hidden")
							panel_scroll.style("overscroll-behavior: contain;")

							with panel_scroll:
								# Give sub-pages a definite full-height host so their own
								# `h-full` + `flex-1` internal scroll layouts can work.
								target = ui.column().classes("w-full h-full min-h-0 min-w-0")

								if panel_id == "general.core":
									general_settings.render(target, ctx)
								elif panel_id == "general.themes":
									theme_settings.render(target, ctx)
								elif panel_id == "general.startup":
									startup_settings.render(target, ctx)
								elif panel_id == "general.users":
									user_management.render(target, ctx)
								elif panel_id == "general.global_vars":
									global_variables_settings.render(target, ctx)
								elif panel_id == "runtime.app_state":
									app_state_view.render(target, ctx)
								elif panel_id == "runtime.online":
									online_status.render(target, ctx)
								elif panel_id == "workers.enabled":
									enabled_workers_settings.render(target, ctx)
								elif panel_id == "workers.scripts":
									scripts_lab.render(target, ctx)
								elif panel_id == "connectivity.routes":
									route_settings.render(target, ctx)
								elif panel_id == "connectivity.tcp":
									tcp_settings.render(target, ctx)
								elif panel_id == "connectivity.twincat":
									twincat_settings.render(target, ctx)
								elif panel_id == "connectivity.itac":
									itac_settings.render(target, ctx)
								elif panel_id == "connectivity.com":
									com_device_settings.render(target, ctx)
								elif panel_id == "connectivity.opcua":
									opcua_settings.render(target, ctx)
								elif panel_id == "connectivity.rest":
									rest_api_settings.render(target, ctx)
								elif panel_id == "languages.manager":
									language_manager.render(target, ctx)
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
