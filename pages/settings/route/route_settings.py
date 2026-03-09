from __future__ import annotations
from typing import Any, Callable

from nicegui import ui

from layout.context import PageContext
from layout.page_registry import get_registered_pages
from pages.settings.route.route_add_dialog import create_add_route_dialog
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from pages.builtin_pages import register_builtin_pages
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


def _get_static_routes() -> list[dict[str, Any]]:
	register_builtin_pages()
	items: list[dict[str, Any]] = []
	for key, route in get_registered_pages().items():
		items.append(
			{
				"key": key,
				"label": route.label,
				"icon": route.icon,
				"always_visible": bool(getattr(route, "always_visible", False)),
				"roles": list(getattr(route, "roles", ()) or []),
			}
		)
	return items


def _move_visible_route_key(route_key: str, delta: int) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	visible_routes = list(nav.visible_routes or [])
	if route_key not in visible_routes:
		return
	index = visible_routes.index(route_key)
	target = index + int(delta)
	if target < 0 or target >= len(visible_routes):
		return
	item = visible_routes.pop(index)
	visible_routes.insert(target, item)
	nav.visible_routes = visible_routes
	save_app_config(cfg)
	_render_static_routes_panel.refresh()
	_render_routes.refresh(scroll_to=None, highlight=None)
	_notify_routes_changed()


def _set_static_route_roles(route_key: str, roles_text: str) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	role_list = [role.strip() for role in str(roles_text or "").split(",") if role.strip()]
	if role_list:
		nav.route_roles[route_key] = role_list
	else:
		nav.route_roles.pop(route_key, None)
	save_app_config(cfg)
	ui.notify("Built-in route permissions updated.", type="positive")
	_render_static_routes_panel.refresh()
	_render_routes.refresh(scroll_to=None, highlight=None)
	_notify_routes_changed()


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
				_render_static_routes_panel()
				_render_routes()


@ui.refreshable
def _render_static_routes_panel() -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	visible_order = list(nav.visible_routes or [])
	static_routes = _get_static_routes()
	role_map = dict(nav.route_roles or {})

	with ui.card().classes("w-full p-4 gap-3"):
		ui.label("Built-in Routes").classes("text-lg font-semibold")
		ui.label(
			"Control whether static application routes appear in navigation. Drawer order still follows ui.navigation.visible_routes."
		).classes("text-sm text-gray-500")

		if not static_routes:
			ui.label("No built-in routes registered.").classes("text-sm text-gray-500")
			return

		for route in static_routes:
			key = str(route.get("key", "") or "")
			label = str(route.get("label", key) or key)
			icon = str(route.get("icon", "insert_drive_file") or "insert_drive_file")
			always_visible = bool(route.get("always_visible", False))
			default_roles = list(route.get("roles", []) or [])
			roles = list(role_map.get(key, default_roles) or [])
			is_visible = always_visible or key in visible_order
			position = visible_order.index(key) + 1 if key in visible_order else None

			with ui.card().classes("w-full p-3 gap-2"):
				with ui.row().classes("w-full items-center justify-between gap-3"):
					with ui.row().classes("items-center gap-3 min-w-0"):
						ui.icon(icon).classes("text-primary")
						with ui.column().classes("gap-0"):
							with ui.row().classes("items-center gap-2"):
								ui.label(label).classes("font-medium")
								ui.label(key).classes("text-xs text-gray-500")
								if always_visible:
									ui.badge("always visible").props("color=info").classes("text-[10px]")
								elif is_visible and position is not None:
									ui.badge(f"position {position}").props("color=positive").classes("text-[10px]")
								else:
									ui.badge("hidden").props("color=warning").classes("text-[10px]")
							if roles:
								ui.label("Roles: " + ", ".join(roles)).classes("text-xs text-gray-400")
					with ui.row().classes("items-center gap-2"):
						checkbox = ui.checkbox("Show", value=is_visible)
						if always_visible:
							checkbox.disable()
						else:
							checkbox.on_value_change(lambda e, route_key=key: _set_static_route_visible(route_key, bool(getattr(e, "value", False))))

				with ui.row().classes("w-full items-center gap-2"):
					role_input = ui.input(
						t("route.allowed_roles", "Allowed roles (comma separated)"),
						value=", ".join(roles),
					).classes("flex-1")
					ui.button(
						t("common.save", "Save"),
						on_click=lambda route_key=key, ri=role_input: _set_static_route_roles(route_key, str(ri.value or "")),
					).props("color=primary")
					if not always_visible:
						ui.button(icon="keyboard_arrow_up", on_click=lambda _=None, route_key=key: _move_visible_route_key(route_key, -1)).props(
							"flat dense"
						).tooltip(t("route.tooltip.move_up", "Move up"))
						ui.button(icon="keyboard_arrow_down", on_click=lambda _=None, route_key=key: _move_visible_route_key(route_key, 1)).props(
							"flat dense"
						).tooltip(t("route.tooltip.move_down", "Move down"))


def _set_static_route_visible(route_key: str, visible: bool) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	visible_routes = list(nav.visible_routes or [])

	if visible and route_key not in visible_routes:
		visible_routes.append(route_key)
	elif not visible:
		visible_routes = [key for key in visible_routes if key != route_key]

	nav.visible_routes = visible_routes
	save_app_config(cfg)
	ui.notify("Built-in route visibility updated.", type="positive")
	_render_static_routes_panel.refresh()
	_render_routes.refresh(scroll_to=None, highlight=None)
	_notify_routes_changed()


@ui.refreshable
def _render_routes(scroll_to: str | None = None, highlight: str | None = None) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation

	routes = nav.custom_routes or []
	role_map = nav.route_roles or {}
	visible_order = list(nav.visible_routes or [])

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
		key = str(route.get("key", "") or "")
		is_visible = key in visible_order
		with ui.row().classes("w-full items-center justify-between gap-3") as summary_row:
			with ui.row().classes("items-center gap-3 min-w-0"):
				ui.icon("drag_indicator").classes("text-gray-500 cursor-grab")
				ui.label(route.get("key", "")).classes("font-medium")
				ui.label(route.get("path", "")).classes("text-xs text-gray-500 truncate")
				if roles:
					ui.label(" - " + ", ".join(roles)).classes("text-xs text-gray-400 truncate")
				if not is_visible:
					ui.badge("not in visible_routes").props("color=warning").classes("text-[10px]")

			with ui.row().classes("items-center gap-2 shrink-0"):
				ui.button(icon="keyboard_arrow_up", on_click=lambda i=idx: _move_route(i, -1)).props(
					"flat dense"
				).tooltip(t("route.tooltip.move_up", "Move up"))
				ui.button(icon="keyboard_arrow_down", on_click=lambda i=idx: _move_route(i, 1)).props(
					"flat dense"
				).tooltip(t("route.tooltip.move_down", "Move down"))
				ui.button(t("common.edit", "Edit"), on_click=toggle).props("flat color=primary").tooltip(t("route.tooltip.edit", "Edit this route"))
				ui.button(t("common.delete", "Delete"), on_click=delete).props("flat color=negative").tooltip(t("route.tooltip.delete", "Delete this route"))
		summary_row.props("draggable=true")
		summary_row.on("dragstart", lambda _e, i=idx: _set_drag_source(i))
		summary_row.on("dragover.prevent", lambda _e: None)
		summary_row.on("drop", lambda _e, i=idx: _drop_route_on(i))

	def render_editor(route: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		key = route.get("key", "")
		roles = route.get("roles", [])
		is_visible = str(key or "") in visible_order
		if is_visible:
			visible_text = f"Visible in drawer order at position {visible_order.index(str(key)) + 1}."
			visible_classes = "text-xs text-green-600"
		else:
			visible_text = "Warning: this route exists but is missing from ui.navigation.visible_routes, so it will not appear in the configured drawer order."
			visible_classes = "text-xs text-amber-600"

		with ui.row().classes("w-full items-center justify-between gap-3"):
			ui.input(t("route.id", "Route id"), value=key).props("readonly borderless").classes("w-full flex-1")
			ui.button(icon="close", on_click=toggle).props("dense flat round")

		with ui.column().classes("w-full gap-2"):
			ui.label(visible_text).classes(visible_classes)
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


_drag_state: dict[str, int | None] = {"source_index": None}


def _set_drag_source(index: int) -> None:
	_drag_state["source_index"] = index


def _drop_route_on(target_index: int) -> None:
	source_index = _drag_state.get("source_index")
	_drag_state["source_index"] = None
	if source_index is None:
		return
	_move_route_to(int(source_index), int(target_index))

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


def _move_route(index: int, delta: int) -> None:
	_move_route_to(index, index + delta)


def _move_route_to(source_index: int, target_index: int) -> None:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	routes = list(nav.custom_routes or [])

	if source_index < 0 or source_index >= len(routes):
		ui.notify(t("route.validation.not_found", "Route not found."), type="negative")
		return

	if target_index < 0 or target_index >= len(routes):
		return

	if source_index == target_index:
		return

	item = routes.pop(source_index)
	routes.insert(target_index, item)
	nav.custom_routes = routes

	moved_key = str(item.get("key", "") or "")
	visible_routes = list(nav.visible_routes or [])
	if moved_key in visible_routes:
		visible_routes.remove(moved_key)
		custom_keys_in_order = [str(route.get("key", "") or "") for route in routes]
		target_visible_index = len(visible_routes)
		for idx, key in enumerate(visible_routes):
			if key not in custom_keys_in_order:
				continue
			current_custom_index = custom_keys_in_order.index(key)
			if current_custom_index >= target_index:
				target_visible_index = idx
				break
		visible_routes.insert(target_visible_index, moved_key)
		nav.visible_routes = visible_routes

	save_app_config(cfg)

	wrapper_id = generate_wrapper_id(ROUTE_LIST.id_prefix, moved_key) if moved_key else None
	_render_static_routes_panel.refresh()
	_render_routes.refresh(scroll_to=wrapper_id, highlight=wrapper_id)
	_notify_routes_changed()




