from __future__ import annotations

import json
import os
from typing import Any, Callable

from nicegui import ui

from layout.context import PageContext
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import DEFAULT_CONFIG_PATH, load_app_config, save_app_config, get_app_config
from pages.settings.tcp_client.tcp_client_add_dialog import create_add_tcp_client_dialog

CLIENT_list = ExpandableList(scroller_id="tcp-client-scroll", id_prefix ="tcp-client-card",
							 expanded_storage_key= "tcp_client_expanded_name",
							 get_key= lambda ep: ep.get("client_id"))


# ---------- config helpers ----------

def _get_routes_and_roles() -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
	cfg = get_app_config()
	nav = cfg.ui.navigation
	return nav.custom_routes, nav.route_roles, nav.visible_routes

def _save(cfg) -> None:
	save_app_config(cfg)

def _parse_int(value: str, message: str) -> int | None:
	try:
		return int(value)
	except (TypeError, ValueError):
		ui.notify(message, type="negative")
		return None


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
				return _add_client(payload)

			_dialog, open_add_dialog = create_add_tcp_client_dialog(on_add=on_add)

			# header (non-scrolling)
			with ui.column().classes("w-full shrink-0 bg-white z-10"):
				with ui.row().classes("w-full items-center justify-between"):
					ui.label("TCP Clients").classes("text-2xl font-bold")
					ui.button("Add client", on_click=open_add_dialog).props("color=primary")
				ui.label("Configure TCP client worker endpoints.").classes("text-sm text-gray-500")

			# scroll area
			with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-2 p-4") as scroller:
				scroller.props(f"id={CLIENT_list.scroller_id}")
				_render_clients()


# ---------- list (collapsible) ----------

@ui.refreshable
def _render_clients(scroll_to: str | None = None, highlight: str | None = None) -> None:
	cfg = get_app_config()
	tcp_cfg = cfg.workers.configs.get("tcp_client", {})
	clients = tcp_cfg.get("clients",{})

	if not clients:
		ui.label("No TCP clients configured yet.").classes("text-sm text-gray-500")
		return

	def refresh() -> None:
		_render_clients.refresh(scroll_to=None, highlight=None)

	def render_summary(tcp_client: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		# compact summary
		with ui.row().classes("w-full items-center justify-between gap-3"):
			with ui.row().classes("items-center gap-3 min-w-0"):
				ui.label(tcp_client.get("client_id","")).classes("font-medium")
				ui.label(f"{tcp_client.get('host', '')}:{tcp_client.get('port', '')}").classes("text-xs text-gray-500")
				flags = []
				if tcp_client.get("connect", True): flags.append("connect")
				if tcp_client.get("auto_reconnect", True): flags.append("reconnect")
				if tcp_client.get("keepalive", True): flags.append("keepalive")
				if tcp_client.get("tcp_nodelay", True): flags.append("no-delay")
				if flags:
					ui.label(" · " + ", ".join(flags)).classes("text-xs text-gray-400 truncate")

			with ui.row().classes("items-center gap-2 shrink-0"):
				ui.button("Edit", on_click=toggle).props("flat color=primary")
				ui.button("Delete", on_click=delete).props("flat color=negative")

	def render_editor(tcp_client: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		cid = tcp_client.get("client_id", "")
		with ui.row().classes("w-full items-center justify-between gap-2"):
			id_box = ui.input("Client ID", value=cid).props("").classes("flex-1")
			ui.button("Close", on_click=toggle).props("flat")

		with ui.column().classes("w-full gap-2"):
			with ui.row().classes("w-full gap-3"):
				host_input = ui.input("Host", value=tcp_client.get("host", "")).classes("flex-1")
				port_input = ui.input("Port", value=str(tcp_client.get("port", ""))).classes("w-40")

			with ui.row().classes("w-full items-center gap-6"):
				connect_input = ui.switch("Connect on startup", value=tcp_client.get("connect", True))
				auto_reconnect_input = ui.switch("Auto reconnect", value=tcp_client.get("auto_reconnect", True))
				keepalive_input = ui.switch("Keepalive", value=tcp_client.get("keepalive", True))
				tcp_no_delay_input = ui.switch("TCP no delay", value=tcp_client.get("tcp_nodelay", True))

			mode_input = ui.input("Mode", value=tcp_client.get("mode", "line")).classes("w-full")
			delimiter_input = ui.input("Delimiter", value=tcp_client.get("delimiter", "\\n")).classes("w-full")
			encoding_input = ui.input("Encoding", value=tcp_client.get("encoding", "utf-8")).classes("w-full")

			with ui.row().classes("w-full gap-3"):
				r_min_input = ui.input("Reconnect min (s)", value=str(tcp_client.get("reconnect_min_s", 1.0))).classes("flex-1")
				r_max_input = ui.input("Reconnect max (s)", value=str(tcp_client.get("reconnect_max_s", 10.0))).classes(
					"flex-1")

			with ui.row().classes("w-full justify-end gap-2 mt-1"):
				ui.button(
					"Save",
					on_click=lambda i=idx, hi=host_input, pi=port_input, ci=connect_input,
									mi=mode_input, di=delimiter_input, ei=encoding_input,
									ari=auto_reconnect_input, rmin=r_min_input, rmax=r_max_input,
									kai=keepalive_input, tni=tcp_no_delay_input:
					_update_client(
						i, hi.value, pi.value, ci.value, mi.value, di.value, ei.value,
						ari.value, rmin.value, rmax.value, kai.value, tni.value)).props("color=primary")

				ui.button("Delete", on_click=delete).props("flat color=negative")

	CLIENT_list.render(clients, render_summary=render_summary, render_editor=render_editor,
					 on_delete=_delete_client,
					 refresh=refresh, scroll_to=scroll_to, highlight=highlight)


# ---------- mutations ----------

def _add_client(payload: dict) -> bool:
	cid = (payload.get("client_id") or "").strip()
	host = (payload.get("host") or "").strip()
	port = (payload.get("port") or "").strip()

	if not cid or not host or not port:
		ui.notify("Client ID, host, and port are required.", type="negative")
		return False

	port_value = _parse_int(port, "Port must be a number.")
	if port_value is None:
		return False

	reconnect_min_value = _parse_float(payload.get("reconnect_min_s", ""), "Reconnect min must be a number.")
	if reconnect_min_value is None:
		return False

	reconnect_max_value = _parse_float(payload.get("reconnect_max_s", ""), "Reconnect max must be a number.")
	if reconnect_max_value is None:
		return False

	cfg = get_app_config()
	tcp_cfg = cfg.workers.configs.setdefault("tcp_client", {})
	clients = list(tcp_cfg.get("clients", {}))

	# optional: prevent duplicate ids
	if any(c.get("client_id") == cid for c in clients):
		ui.notify("Client ID already exists.", type="negative")
		return False

	clients.append({
		"client_id": cid,
		"host": host,
		"port": port_value,
		"connect": bool(payload.get("connect", True)),
		"mode": payload.get("mode") or "line",
		"delimiter": payload.get("delimiter") or "\\n",
		"encoding": payload.get("encoding") or "utf-8",
		"auto_reconnect": bool(payload.get("auto_reconnect", True)),
		"reconnect_min_s": reconnect_min_value,
		"reconnect_max_s": reconnect_max_value,
		"keepalive": bool(payload.get("keepalive", True)),
		"tcp_nodelay": bool(payload.get("tcp_nodelay", True)),
	})

	tcp_cfg["clients"] = clients
	save_app_config(cfg)
	ui.notify("TCP client added.", type="positive")

	wrapper_id = generate_wrapper_id(CLIENT_list.id_prefix, cid)
	_render_clients.refresh(scroll_to=wrapper_id, highlight=wrapper_id)
	return True


def _delete_client(index: int) -> None:
	cfg = get_app_config()
	tcp_cfg = cfg.workers.configs.setdefault("tcp_client", {})
	clients = list(tcp_cfg.get("clients", {}))
	if index < 0 or index >= len(clients):
		ui.notify("Client not found.", type="negative")
		return

	removed = clients.pop(index)
	tcp_cfg["clients"] = clients
	save_app_config(cfg)
	ui.notify("TCP client removed.", type="positive")

	# close editor if it was open
	opened = ui.context.client.storage.get("tcp_clients_expanded_id")
	if opened and opened == removed.get("client_id"):
		ui.context.client.storage["tcp_clients_expanded_id"] = None

	_render_clients.refresh()


def _update_client(
	index: int,
	host: str,
	port: str,
	connect: bool,
	mode: str,
	delimiter: str,
	encoding: str,
	auto_reconnect: bool,
	reconnect_min_s: str,
	reconnect_max_s: str,
	keepalive: bool,
	tcp_no_delay: bool,
) -> None:
	port_value = _parse_int(port, "Port must be a number.")
	if port_value is None:
		return
	reconnect_min_value = _parse_float(reconnect_min_s, "Reconnect min must be a number.")
	if reconnect_min_value is None:
		return
	reconnect_max_value = _parse_float(reconnect_max_s, "Reconnect max must be a number.")
	if reconnect_max_value is None:
		return

	cfg = get_app_config()
	tcp_cfg = cfg.workers.configs.setdefault("tcp_client", {})
	clients = list(tcp_cfg.get("clients", {}))
	if index < 0 or index >= len(clients):
		ui.notify("Client not found.", type="negative")
		return

	current = clients[index]
	clients[index] = {
		"client_id": current.get("client_id", ""),
		"host": host,
		"port": port_value,
		"connect": bool(connect),
		"mode": mode or "line",
		"delimiter": delimiter or "\\n",
		"encoding": encoding or "utf-8",
		"auto_reconnect": bool(auto_reconnect),
		"reconnect_min_s": reconnect_min_value,
		"reconnect_max_s": reconnect_max_value,
		"keepalive": bool(keepalive),
		"tcp_nodelay": bool(tcp_no_delay),
	}

	tcp_cfg["clients"] = clients
	save_app_config(cfg)
	ui.notify("TCP client updated.", type="positive")
	_render_clients.refresh()
