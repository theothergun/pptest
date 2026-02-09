from __future__ import annotations

import json
import os
from typing import Any, Callable

from nicegui import ui

from layout.context import PageContext
from pages.settings.rest_api.rest_api_add_dialog import create_add_rest_endpoint_dialog
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config, get_app_config

REST_list = ExpandableList(scroller_id="rest-api-scroll", id_prefix ="rest-api-card",
						   expanded_storage_key= "rest_api_expanded_name",
						   get_key= lambda ep: ep.get("name"))

# ---------- config helpers ----------
def _get_routes_and_roles() -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	return nav.custom_routes, nav.route_roles, nav.visible_routes

def _save(cfg) -> None:
	save_app_config(cfg)



def _parse_headers(value: str) -> dict[str, Any] | None:
	if not value:
		return {}
	try:
		parsed = json.loads(value)
	except json.JSONDecodeError:
		ui.notify("Headers must be valid JSON.", type="negative")
		return None
	if not isinstance(parsed, dict):
		ui.notify("Headers JSON must be an object.", type="negative")
		return None
	return parsed


def _parse_float(value: str, message: str) -> float | None:
	try:
		return float(value)
	except (TypeError, ValueError):
		ui.notify(message, type="negative")
		return None


# ---------- page ----------

def render(container: ui.element, ctx: PageContext) -> None:
	with container.classes("w-full h-full min-h-0 overflow-hidden"):
		with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col"):

			def on_add(payload: dict) -> bool:
				return _add_endpoint(payload)

			_dialog, open_add_dialog = create_add_rest_endpoint_dialog(on_add=on_add)

			# header (non-scrolling)
			with ui.column().classes("w-full shrink-0 bg-white z-10"):
				with ui.row().classes("w-full items-center justify-between"):
					ui.label("REST API").classes("text-2xl font-bold")
					ui.button("Add endpoint", on_click=open_add_dialog).props("color=primary")
				ui.label("Configure REST API worker endpoints.").classes("text-sm text-gray-500")

			# scroll area
			with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-2 p-4") as scroller:
				scroller.props(f"id={REST_list.scroller_id}")
				_render_endpoints()


# ---------- list (collapsible) ----------

@ui.refreshable
def _render_endpoints(scroll_to: str | None = None, highlight: str | None = None) -> None:
	cfg = get_app_config()
	rest_cfg = cfg.workers.configs.get("rest_api",{})
	endpoints = rest_cfg.get("endpoints", [])

	if not endpoints:
		ui.label("No REST API endpoints configured yet.").classes("text-sm text-gray-500")
		return

	def refresh() -> None:
		_render_endpoints.refresh(scroll_to=None, highlight=None)

	def render_summary(ep: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		# summary row
		with ui.row().classes("w-full items-center justify-between gap-3"):
			with ui.row().classes("items-center gap-3 min-w-0"):
				ui.label(ep.get("name","")).classes("font-medium")
				ui.label(ep.get("base_url", "")).classes("text-xs text-gray-500 truncate")
				ui.label(f"timeout {ep.get('timeout_s', 10.0)}s").classes("text-xs text-gray-400")

				if not ep.get("verify_ssl", True):
					ui.label("SSL off").classes("text-xs text-orange-600")

			with ui.row().classes("items-center gap-2 shrink-0"):
				ui.button("Edit", on_click=toggle).props("flat color=primary")
				ui.button("Delete", on_click=delete).props("flat color=negative")

	def render_editor(ep: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		name = ep.get("name", "")

		with ui.row().classes("w-full items-center justify-between gap-2"):
			name_input = ui.input("Name", value=name).classes("flex-1")
			ui.button("Close", on_click=toggle).props("flat color=primary")

		# editor fields
		with ui.column().classes("w-full gap-2"):
			base_url_input = ui.input("Base URL", value=ep.get("base_url", "")).classes("w-full")
			# show JSON pretty formatted
			headers_input = ui.textarea("Headers (JSON)",value=json.dumps(ep.get("headers", {}), indent=2),
			).classes("w-full")
			timeout_input = ui.input("Timeout (s)", value=str(ep.get("timeout_s", 10.0))).classes("w-full")
			verify_ssl_input = ui.switch("Verify SSL", value=ep.get("verify_ssl", True))

			with ui.row().classes("w-full justify-end gap-2 mt-1"):
				ui.button("Save", on_click=lambda i=idx, na=name_input, bi=base_url_input, hi=headers_input,
						ti=timeout_input, vi=verify_ssl_input:_update_endpoint(i, na.value, bi.value, hi.value,
						ti.value, vi.value)).props("color=primary")

				ui.button("Delete", on_click=delete).props("flat color=negative")

	REST_list.render(endpoints, render_summary=render_summary, render_editor=render_editor, on_delete=_delete_endpoint,
					 refresh=refresh, scroll_to=scroll_to, highlight=highlight)


# ---------- mutations ----------

def _add_endpoint(payload: dict) -> bool:
	name = (payload.get("name") or "").strip()
	base_url = (payload.get("base_url") or "").strip()
	headers_raw = payload.get("headers_raw") or ""
	timeout_s = payload.get("timeout_s") or "10"
	verify_ssl = bool(payload.get("verify_ssl", True))

	if not name or not base_url:
		ui.notify("Name and base URL are required.", type="negative")
		return False

	headers = _parse_headers(headers_raw)
	if headers is None:
		return False

	timeout_value = _parse_float(timeout_s, "Timeout must be a number.")
	if timeout_value is None:
		return False

	cfg = get_app_config()
	rest_cfg = cfg.workers.configs.setdefault("rest_api",{})
	endpoints = list(rest_cfg.get("endpoints", []))

	# optional: prevent duplicate endpoint names
	if any(e.get("name") == name for e in endpoints):
		ui.notify("Endpoint name already exists.", type="negative")
		return False

	endpoints.append({
		"name": name,
		"base_url": base_url,
		"headers": headers,
		"timeout_s": timeout_value,
		"verify_ssl": verify_ssl,
	})
	rest_cfg["endpoints"] = endpoints
	save_app_config(cfg)
	ui.notify("REST endpoint added.", type="positive")

	wid = generate_wrapper_id(REST_list.id_prefix, name)
	_render_endpoints.refresh(scroll_to=wid, highlight=wid)
	return True


def _delete_endpoint(index: int) -> None:
	cfg = get_app_config()
	rest_cfg = cfg.workers.configs.setdefault("rest_api", {})
	endpoints = list(rest_cfg.get("endpoints", []))
	if index < 0 or index >= len(endpoints):
		ui.notify("Endpoint not found.", type="negative")
		return

	removed = endpoints.pop(index)
	rest_cfg["endpoints"] = endpoints
	save_app_config(cfg)
	ui.notify("REST endpoint removed.", type="positive")

	opened = ui.context.client.storage.get("rest_endpoints_expanded_name")
	if opened and opened == removed.get("name"):
		ui.context.client.storage["rest_endpoints_expanded_name"] = None

	_render_endpoints.refresh()


def _update_endpoint(
	index: int,
	name: str,
	base_url: str,
	headers_raw: str,
	timeout_s: str,
	verify_ssl: bool,
) -> None:
	headers = _parse_headers(headers_raw)
	if headers is None:
		return

	timeout_value = _parse_float(timeout_s, "Timeout must be a number.")
	if timeout_value is None:
		return

	cfg = get_app_config()
	rest_cfg = cfg.workers.configs.setdefault("rest_api", {})
	endpoints = list(rest_cfg.get("endpoints", []))
	if index < 0 or index >= len(endpoints):
		ui.notify("Endpoint not found.", type="negative")
		return

	endpoints[index] = {
		"name": name,
		"base_url": base_url,
		"headers": headers,
		"timeout_s": timeout_value,
		"verify_ssl": bool(verify_ssl),
	}

	rest_cfg["endpoints"] = endpoints
	save_app_config(cfg)
	ui.notify("REST endpoint updated.", type="positive")
	_render_endpoints.refresh()
