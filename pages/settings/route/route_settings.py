from __future__ import annotations
from typing import Any, Callable

from nicegui import ui

from layout.context import PageContext
from layout.router import Route
from pages.settings.route.route_add_dialog import create_add_route_dialog
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import get_app_config, save_app_config
from services.i18n import t
from loguru import logger

ROUTE_LIST = ExpandableList(scroller_id="routes-scroll", id_prefix ="route-card",
							expanded_storage_key= "route_expanded_name",
							get_key= lambda ep: ep.get("key"))

_on_routes_changed: Callable[[], None] | None = None

def set_on_routes_changed(cb: Callable[[], None]) -> None:
	global _on_routes_changed
	_on_routes_changed = cb

def _notify_routes_changed() -> None:
	if _on_routes_changed:
		_on_routes_changed()

def _get_routes_and_roles() -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	return nav.custom_routes, nav.route_roles, nav.visible_routes

def _save(cfg) -> None:
	save_app_config(cfg)


def render(container: ui.element, ctx: PageContext) -> None:
	logger.debug(f"[render] - route_settings_render")
	set_on_routes_changed(ctx.refresh_drawer)
	with container.classes("w-full h-full min-h-0 overflow-hidden"):
		# Full height layout so only the list scrolls
		with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col"):
			# --- Create dialog once ---
			def on_add_route(key: str, label: str, icon: str, path: str, roles: str) -> bool:
				return _add_route(key, label, icon, path, roles)

			_dialog, open_add_dialog = create_add_route_dialog(on_add=on_add_route)

			# --- Sticky header (never scrolls) ---
			with ui.column().classes("w-full shrink-0 z-10"):
				with ui.row().classes("w-full items-center justify-between"):
					ui.label(t("route.settings_title", "Route Settings")).classes("text-2xl font-bold")
					ui.button(t("route.add_route", "Add route"), on_click=open_add_dialog).props("color=primary").tooltip(t("route.tooltip.add", "Add a new custom route"))
				ui.label(t("route.settings_subtitle", "Add / Edit custom routes (including subfolders like packaging/packaging.py).")).classes(
					"text-sm text-gray-500"
				)

			with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-2 p-6 pl-1") as routes_scroll:
				routes_scroll.props(f"id={ROUTE_LIST.scroller_id}")
				_render_routes()


@ui.refreshable
def _render_routes(scroll_to: str | None = None, highlight: str | None = None) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation

	routes = nav.custom_routes or []
	role_map = nav.route_roles or {}

	if not routes:
		ui.label(t("route.none", "No custom routes configured yet.")).classes("text-sm text-gray-500")
		return

	# Enrich route dicts so UI can use route["roles"]
	routes_view: list[dict[str, Any]] = []
	for r in routes:
		k = r.get("key", "")
		rr = dict(r)
		rr["roles"] = role_map.get(k, [])
		routes_view.append(rr)

	def refresh() -> None:
		_render_routes.refresh(scroll_to=None, highlight=None)

	def render_summary(route: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		roles = route.get("roles", [])
		with ui.row().classes("w-full items-center justify-between gap-3"):
			with ui.row().classes("items-center gap-3 min-w-0"):
				ui.label(route.get("key", "")).classes("font-medium")
				ui.label(route.get("path", "")).classes("text-xs text-gray-500 truncate")
				if roles:
					ui.label(" - " + ", ".join(roles)).classes("text-xs text-gray-400 truncate")

			with ui.row().classes("items-center gap-2 shrink-0"):
				ui.button(t("common.edit", "Edit"), on_click=toggle).props("flat color=primary").tooltip(t("route.tooltip.edit", "Edit this route"))
				ui.button(t("common.delete", "Delete"), on_click=delete).props("flat color=negative").tooltip(t("route.tooltip.delete", "Delete this route"))

	def render_editor(route: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		key = route.get("key", "")
		roles = route.get("roles", [])

		with ui.row().classes("w-full items-center justify-between gap-3"):
			ui.input(t("route.id", "Route id"), value=key).props("readonly borderless").classes("w-full flex-1")
			ui.button(icon="close", on_click=toggle).props("dense flat round")

		with ui.column().classes("w-full gap-2"):
			with ui.row().classes("w-full items-center gap-3"):
				label_input = ui.input(t("common.label", "Label"), value=route.get("label", "")).classes("flex-1")
				icon_input = ui.input(t("common.icon", "Icon"), value=route.get("icon", "")).classes("flex-1")

			with ui.row().classes("w-full items-center gap-4"):
				path_input = ui.input(t("route.file_path", "File path"), value=route.get("path", "")).classes("flex-1")
				roles_input = ui.input(t("route.allowed_roles", "Allowed roles (comma separated)"), value=", ".join(roles)).classes("flex-1")

			with ui.row().classes("w-full items-center justify-end gap-2"):
				ui.button(
					t("common.save", "Save"),
					on_click=lambda i=idx, li=label_input, ii=icon_input, pi=path_input, ri=roles_input:
						_update_route(i, li.value, ii.value, pi.value, ri.value),
				).props("color=primary")
				ui.button("Delete", on_click=delete).props("color=negative flat")

	ROUTE_LIST.render(routes_view, render_summary=render_summary, render_editor=render_editor,
					  on_delete=_delete_route, refresh=refresh, scroll_to=scroll_to, highlight=highlight, )

def _add_route(key: str,label: str,	icon: str, path: str, roles: str) -> bool:
	if not key or not path:
		ui.notify(t("route.validation.required", "Route key and file path are required."), type="negative")
		return False

	cfg = get_app_config()
	nav = cfg.ui.navigation

	routes = list(nav.custom_routes or [])
	routes.append(
		{
			"key": key,
			"label": label or key,
			"icon": icon or "insert_drive_file",
			"path": path,
		}
	)
	nav.custom_routes = routes
	# roles mapping
	role_list = [r.strip() for r in (roles or "").split(",") if r.strip()]
	if role_list:
		nav.route_roles[key] = role_list
	else:
		nav.route_roles.pop(key, None)

	# visible routes
	if key not in nav.visible_routes:
		nav.visible_routes.append(key)

	save_app_config(cfg)

	ui.notify(t("route.notify.added", "Route added."), type="positive")
	wrapper_id = generate_wrapper_id(ROUTE_LIST.id_prefix, key)
	_render_routes.refresh(scroll_to=wrapper_id, highlight=wrapper_id)
	_notify_routes_changed()
	return True


def _delete_route(index: int) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation

	routes = list(nav.custom_routes or [])
	if index < 0 or index >= len(routes):
		ui.notify(t("route.validation.not_found", "Route not found."), type="negative")
		return
	removed = routes.pop(index)
	nav.custom_routes = routes
	key = removed.get("key")
	if key:
		nav.route_roles.pop(key, None)

	save_app_config(cfg)
	ui.notify(t("route.notify.removed", "Route removed."), type="positive")
	_render_routes.refresh(scroll_to=None, highlight=None)
	_notify_routes_changed()


def _update_route(index: int, label: str, icon: str, path: str, roles: str) -> None:
	if not path:
		ui.notify(t("route.validation.file_path_required", "File path is required."), type="negative")
		return

	cfg = get_app_config()
	nav = cfg.ui.navigation

	routes = list(nav.custom_routes or [])
	if index < 0 or index >= len(routes):
		ui.notify(t("route.validation.not_found", "Route not found."), type="negative")
		return

	current = routes[index]
	key = current.get("key", "")
	routes[index] = {
		"key": key,
		"label": label or key,
		"icon": icon or "insert_drive_file",
		"path": path,
	}
	nav.custom_routes = routes
	role_list = [r.strip() for r in (roles or "").split(",") if r.strip()]
	if role_list:
		nav.route_roles[key] = role_list
	else:
		nav.route_roles.pop(key, None)

	save_app_config(cfg)
	ui.notify(t("route.notify.updated", "Route updated."), type="positive")
	_render_routes.refresh(scroll_to=None, highlight=None)
	_notify_routes_changed()




