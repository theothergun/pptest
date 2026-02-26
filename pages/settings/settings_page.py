from __future__ import annotations

from nicegui import ui

from layout.main_area import PageContext
from layout.app_style import button_classes, button_props
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
from pages.settings import blockly_builder
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
    logger.debug("[render] - settings_page_render_start")
    container.style("overflow: hidden !important;")
    container.style("min-height: 0 !important;")

    with container:
        with ui.column().classes("w-full h-full min-h-0 min-w-0"):
            render_settings_header(
                ctx,
                title=t("settings.title", "Settings"),
                subtitle=t("settings.subtitle", "Manage application settings and worker configuration."),
            )

            with ui.column().classes("w-full flex-1 min-h-0 min-w-0 app-panel p-3"):
                with ui.row().classes("w-full flex-1 min-h-0 min-w-0 overflow-hidden gap-3 no-wrap items-stretch"):
                    left_col = ui.column().classes(
                        "w-[290px] min-w-[240px] h-full min-h-0 overflow-y-auto shrink-0 app-panel p-2"
                    )
                    left_col.style("overscroll-behavior: contain;")

                    nodes = [
                        {"id": "general", "label": f"⚙️ {t('settings.general.title', 'General')}", "children": [
                            {"id": "general.core", "label": f"🛠️ {t('settings.general.core', 'General Settings')}"},
                            {"id": "general.themes", "label": f"🎨 {t('settings.general.themes', 'Color Themes')}"},
                            {"id": "general.startup", "label": f"🚀 {t('settings.general.startup', 'Startup')}"},
                            {"id": "general.users", "label": f"👤 {t('settings.general.users', 'User Management')}"},
                            {"id": "general.global_vars", "label": f"🌐 {t('settings.general.global_vars', 'Global Variables')}"},
                        ]},
                        {"id": "runtime", "label": f"🧠 {t('settings.runtime.title', 'Runtime')}", "children": [
                            {"id": "runtime.app_state", "label": f"📦 {t('settings.runtime.app_state', 'Application Variables')}"},
                            {"id": "runtime.online", "label": f"☁️ {t('settings.runtime.online', 'Online Status')}"},
                        ]},
                        {"id": "workers", "label": f"👷 {t('settings.workers.title', 'Workers')}", "children": [
                            {"id": "workers.enabled", "label": f"✅ {t('settings.workers.enabled', 'Enabled Workers')}"},
                            {"id": "workers.scripts", "label": f"💻 {t('settings.workers.scripts', 'Scripts')}"},
                            {"id": "workers.blockly", "label": "🧩 Blockly Builder"},
                        ]},
                        {"id": "connectivity", "label": f"🔌 {t('settings.connectivity.title', 'Connectivity')}", "children": [
                            {"id": "connectivity.routes", "label": f"🧭 {t('settings.connectivity.routes', 'Routes')}"},
                            {"id": "connectivity.tcp", "label": f"🛰️ {t('settings.connectivity.tcp', 'TCP Clients')}"},
                            {"id": "connectivity.twincat", "label": f"🧩 {t('settings.connectivity.twincat', 'TwinCAT')}"},
                            {"id": "connectivity.itac", "label": f"🏭 {t('settings.connectivity.itac', 'iTAC')}"},
                            {"id": "connectivity.com", "label": f"🔗 {t('settings.connectivity.com', 'COM Device')}"},
                            {"id": "connectivity.opcua", "label": f"📡 {t('settings.connectivity.opcua', 'OPC UA')}"},
                            {"id": "connectivity.rest", "label": f"🌐 {t('settings.connectivity.rest', 'REST APIs')}"},
                        ]},
                        {"id": "languages", "label": f"🌍 {t('settings.languages.title', 'Languages')}", "children": [
                            {"id": "languages.manager", "label": f"🗣️ {t('settings.languages.manager', 'Language Manager')}"},
                        ]},
                        {"id": "dummy", "label": f"🧩 {t('dummy.languages.title', 'Dummy')}", "children": [
                            {"id": "dummy.config", "label": f"🛠️ {t('dummy.languages.config', 'Config')}"},
                            {"id": "dummy.test_result", "label": f"📈 {t('dummy.languages.test_result', 'Test Results')}"},
                            {"id": "dummy.manual_test", "label": f"🔬 {t('dummy.languages.manual_test', 'Manual Test')}"},
                        ]},
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

                    right_col = ui.column().classes("flex-1 h-full min-h-0 min-w-0 overflow-hidden")

                    def render_panel(panel_id: str) -> None:
                        logger.info(f"[render_panel] - panel_selected - panel_id={panel_id}")
                        right_col.clear()

                        with right_col:
                            panel_scroll = ui.column().classes(
                                "w-full h-full flex-1 min-h-0 min-w-0 overflow-y-auto overflow-x-hidden app-panel p-3"
                            )
                            panel_scroll.style("overscroll-behavior: contain;")

                            with panel_scroll:
                                target = ui.column().classes("w-full h-full min-h-0 min-w-0")
                                mapping = {
                                    "general.core": general_settings.render,
                                    "general.themes": theme_settings.render,
                                    "general.startup": startup_settings.render,
                                    "general.users": user_management.render,
                                    "general.global_vars": global_variables_settings.render,
                                    "runtime.app_state": app_state_view.render,
                                    "runtime.online": online_status.render,
                                    "workers.enabled": enabled_workers_settings.render,
                                    "workers.scripts": scripts_lab.render,
                                    "workers.blockly": blockly_builder.render,
                                    "connectivity.routes": route_settings.render,
                                    "connectivity.tcp": tcp_settings.render,
                                    "connectivity.twincat": twincat_settings.render,
                                    "connectivity.itac": itac_settings.render,
                                    "connectivity.com": com_device_settings.render,
                                    "connectivity.opcua": opcua_settings.render,
                                    "connectivity.rest": rest_api_settings.render,
                                    "languages.manager": language_manager.render,
                                    "dummy.config": render_dummy_config,
                                    "dummy.test_result": render_dummy_results,
                                    "dummy.manual_test": render_manual_dummy_test,
                                }
                                renderer = mapping.get(panel_id)
                                if renderer:
                                    renderer(target, ctx)
                                else:
                                    ui.label(t("settings.select_hint", "Select a section from the tree.")).classes(
                                        "text-sm text-[var(--text-secondary)]"
                                    )

                    def on_select(e) -> None:
                        node_id = getattr(e, "value", None)
                        logger.debug(f"[on_select] - tree_node_selected - node_id={node_id}")
                        if node_id in leaf_ids:
                            render_panel(node_id)

                    with left_col:
                        with ui.row().classes("w-full items-center justify-between pb-1"):
                            ui.label(t("settings.sections", "Sections")).classes("text-sm text-[var(--text-secondary)]")
                            with ui.row().classes("items-center gap-1"):
                                ui.button(icon="unfold_more", on_click=lambda: nav_tree.expand()).props(
                                    button_props("neutral") + " dense"
                                ).classes(button_classes())
                                ui.button(icon="unfold_less", on_click=lambda: nav_tree.collapse()).props(
                                    button_props("neutral") + " dense"
                                ).classes(button_classes())
                        nav_tree = ui.tree(nodes, label_key="label", on_select=on_select).classes("w-full")
                        nav_tree.props("dense")
                        nav_tree.expand()

                    render_panel("general.core")
