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
from pages.settings import barfi_builder
from pages.settings.route import route_settings
from pages.settings.tcp_client import tcp_settings
from pages.settings import twincat_settings
from pages.settings import itac_settings
from pages.settings import com_device_settings
from pages.settings import opcua_settings
from pages.settings import rest_api_settings
from pages.settings import language_manager
from pages.dummy.config import render as render_dummy_config
from pages.dummy.results_view import render as render_dummy_results
from pages.dummy.test_view import render as render_manual_dummy_test
from services.i18n import t
from loguru import logger


def render(container: ui.element, ctx: PageContext) -> None:
	logger.debug(f"[render] - settings_page_render_start")
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
								{"id": "workers.barfi", "label": "🧱 Barfi Builder"},
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
						{
							"id": "dummy",
							"label": f"🧩 {t('dummy.languages.title', 'Dummy')}",
							"children": [
								{
									"id": "dummy.config",
									"label": f"🛠️ {t('dummy.languages.config', 'Config')}"
								},
								{
									"id": "dummy.test_result",
									"label": f"📈 {t('dummy.languages.test_result', 'Test Results')}"
								},
								{
									"id": "dummy.manual_test",
									"label": f"🔬 {t('dummy.languages.manual_test', 'Manual Test')}"
								},
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
						logger.info(f"[render_panel] - panel_selected - panel_id={panel_id}")
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
								elif panel_id == "workers.barfi":
									barfi_builder.render(target, ctx)
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
								elif panel_id == "dummy.config":
									render_dummy_config(target, ctx)
								elif panel_id == "dummy.test_result":
									render_dummy_results(target, ctx)
								elif panel_id == "dummy.manual_test":
									render_manual_dummy_test(target, ctx)
								else:
									ui.label(t("settings.select_hint", "Select a section from the tree.")).classes("text-sm text-gray-500")

					def on_select(e) -> None:
						node_id = getattr(e, "value", None)
						logger.debug(f"[on_select] - tree_node_selected - node_id={node_id}")
						if node_id in leaf_ids:
							render_panel(node_id)

					with left_col:
						with ui.row().classes("w-full items-end justify-between gap-1 pb-0 mt-0"):
							ui.label(t("settings.sections", "Sections")).classes("text-sm text-gray-500 leading-none")
							with ui.row().classes("items-center gap-1"):
								ui.button("+", on_click=lambda: nav_tree.expand()).props("dense flat size=sm").tooltip(t("settings.tooltip.expand", "Expand all sections"))
								ui.button("-", on_click=lambda: nav_tree.collapse()).props("dense flat size=sm").tooltip(t("settings.tooltip.collapse", "Collapse all sections"))
						nav_tree = ui.tree(nodes, label_key="label", on_select=on_select).classes("w-full mt-0 pt-0")
						nav_tree.props("dense")
						nav_tree.expand()

					# default view
					render_panel("general.core")
