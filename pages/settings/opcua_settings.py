from __future__ import annotations

import json
from typing import Callable

from nicegui import ui

from layout.context import PageContext
from pages.utils.expandable_list import ExpandableList
from pages.utils.scroll_fx import generate_wrapper_id
from services.app_config import get_app_config, save_app_config

OPCUA_LIST = ExpandableList(
	scroller_id="opcua-scroll",
	id_prefix="opcua-card",
	expanded_storage_key="opcua_expanded_name",
	get_key=lambda ep: ep.get("name", ""),
)


def _parse_float(value: str, message: str) -> float | None:
	try:
		return float(str(value).strip())
	except Exception:
		ui.notify(message, type="negative")
		return None


def _parse_nodes(value: str) -> list[dict] | None:
	import json
	raw = (value or "").strip()
	if not raw:
		return []
	try:
		parsed = json.loads(raw)
	except Exception:
		ui.notify("Nodes must be valid JSON.", type="negative")
		return None
	if not isinstance(parsed, list):
		ui.notify("Nodes JSON must be a list.", type="negative")
		return None
	for item in parsed:
		if not isinstance(item, dict):
			ui.notify("Each node entry must be an object.", type="negative")
			return None
	return parsed


def render(container: ui.element, _ctx: PageContext) -> None:
	with container.classes("w-full h-full min-h-0 overflow-hidden"):
		with ui.column().classes("w-full h-full min-h-0 overflow-hidden flex flex-col"):
			with ui.row().classes("w-full items-center justify-between"):
				ui.label("OPC UA").classes("text-2xl font-bold")
				ui.button("Add endpoint", on_click=_open_add_dialog).props("color=primary")
			ui.label("Configure OPC UA worker endpoints.").classes("text-sm text-gray-500")

			with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto gap-2 p-2") as scroller:
				scroller.props(f"id={OPCUA_LIST.scroller_id}")
				_render_endpoints()


@ui.refreshable
def _render_endpoints(scroll_to: str | None = None, highlight: str | None = None) -> None:
	cfg = get_app_config()
	opc_cfg = cfg.workers.configs.setdefault("opcua", {})
	endpoints = list(opc_cfg.get("endpoints", []))

	if not endpoints:
		ui.label("No OPC UA endpoints configured yet.").classes("text-sm text-gray-500")
		return

	def refresh() -> None:
		_render_endpoints.refresh(scroll_to=None, highlight=None)

	def render_summary(ep: dict, _idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		with ui.row().classes("w-full items-center justify-between gap-3"):
			with ui.row().classes("items-center gap-3 min-w-0"):
				ui.label(ep.get("name", "")).classes("font-medium")
				ui.label(ep.get("server_url", "")).classes("text-xs text-gray-500 truncate")
				if ep.get("auto_connect", False):
					ui.label("auto-connect").classes("text-xs text-gray-400")
			with ui.row().classes("items-center gap-2 shrink-0"):
				ui.button("Edit", on_click=toggle).props("flat color=primary")
				ui.button("Delete", on_click=delete).props("flat color=negative")

	def render_editor(ep: dict, idx: int, toggle: Callable[[], None], delete: Callable[[], None]) -> None:
		with ui.row().classes("w-full items-center justify-between gap-2"):
			ui.input("Name", value=ep.get("name", "")).props("readonly borderless").classes("flex-1")
			ui.button("Close", on_click=toggle).props("flat")

		with ui.row().classes("w-full gap-3"):
			server_url = ui.input("Server URL", value=ep.get("server_url", "")).classes("flex-1")
			timeout_s = ui.input("Timeout (s)", value=str(ep.get("timeout_s", 5.0))).classes("w-52")
			auto_connect = ui.switch("Auto connect", value=ep.get("auto_connect", False))
			visible_on_device_panel = ui.switch(
				"Visible on device panel",
				value=bool(ep.get("visible_on_device_panel", False)),
			)

		with ui.row().classes("w-full gap-3"):
			security_policy = ui.input("Security policy", value=ep.get("security_policy", "None")).classes("flex-1")
			security_mode = ui.input("Security mode", value=ep.get("security_mode", "None")).classes("flex-1")

		with ui.row().classes("w-full gap-3"):
			username = ui.input("Username", value=ep.get("username", "")).classes("flex-1")
			password = ui.input("Password", value=ep.get("password", "")).props("type=password").classes("flex-1")
		nodes = ui.textarea(
			"Nodes (JSON list: [{\"node_id\":\"ns=2;s=Main.CURRENTIP\",\"alias\":\"CurrentIp\",\"poll_ms\":500}])",
			value=json.dumps(ep.get("nodes", []), indent=2),
		).classes("w-full")

		with ui.row().classes("w-full justify-end gap-2"):
			ui.button(
				"Save",
				on_click=lambda i=idx, n=ep.get("name", ""), u=server_url, to=timeout_s, ac=auto_connect, sp=security_policy, sm=security_mode, un=username, pw=password, nd=nodes:
				_update_endpoint(i, n, u.value, to.value, bool(ac.value), sp.value, sm.value, un.value, pw.value, nd.value, bool(visible_on_device_panel.value)),
			).props("color=primary")
			ui.button("Delete", on_click=delete).props("flat color=negative")

	OPCUA_LIST.render(
		endpoints,
		render_summary=render_summary,
		render_editor=render_editor,
		on_delete=_delete_endpoint,
		refresh=refresh,
		scroll_to=scroll_to,
		highlight=highlight,
	)


def _open_add_dialog() -> None:
	d = ui.dialog()
	with d, ui.card().classes("w-[780px] max-w-[95vw]"):
		ui.label("Add OPC UA endpoint").classes("text-lg font-semibold")
		name = ui.input("Name").classes("w-full")
		server_url = ui.input("Server URL", value="opc.tcp://127.0.0.1:4840").classes("w-full")
		timeout_s = ui.input("Timeout (s)", value="5.0").classes("w-full")
		auto_connect = ui.switch("Auto connect", value=False)
		visible_on_device_panel = ui.switch("Visible on device panel", value=False)
		security_policy = ui.input("Security policy", value="None").classes("w-full")
		security_mode = ui.input("Security mode", value="None").classes("w-full")
		username = ui.input("Username").classes("w-full")
		password = ui.input("Password").props("type=password").classes("w-full")
		nodes = ui.textarea(
			"Nodes (JSON list: [{\"node_id\":\"ns=2;s=Main.CURRENTIP\",\"alias\":\"CurrentIp\",\"poll_ms\":500}])",
			value="[]",
		).classes("w-full")

		with ui.row().classes("w-full justify-end gap-2"):
			ui.button("Cancel", on_click=d.close).props("flat")
			ui.button(
				"Add",
				on_click=lambda: _add_endpoint(
					d,
					name.value,
					server_url.value,
					timeout_s.value,
					bool(auto_connect.value),
					security_policy.value,
					security_mode.value,
					username.value,
					password.value,
					nodes.value,
					bool(visible_on_device_panel.value),
				),
			).props("color=primary")
	d.open()


def _add_endpoint(
	dlg: ui.dialog,
	name: str,
	server_url: str,
	timeout_s: str,
	auto_connect: bool,
	security_policy: str,
	security_mode: str,
	username: str,
	password: str,
	nodes_raw: str,
	visible_on_device_panel: bool,
) -> None:
	if not name.strip() or not server_url.strip():
		ui.notify("Name and server URL are required.", type="negative")
		return
	timeout_v = _parse_float(timeout_s, "Timeout must be a number.")
	if timeout_v is None:
		return
	nodes_v = _parse_nodes(nodes_raw)
	if nodes_v is None:
		return

	cfg = get_app_config()
	opc_cfg = cfg.workers.configs.setdefault("opcua", {})
	endpoints = list(opc_cfg.get("endpoints", []))
	if any(e.get("name") == name for e in endpoints):
		ui.notify("OPC UA endpoint name already exists.", type="negative")
		return

	endpoints.append(
		{
			"name": name.strip(),
			"server_url": server_url.strip(),
			"timeout_s": timeout_v,
			"auto_connect": bool(auto_connect),
			"security_policy": security_policy or "None",
			"security_mode": security_mode or "None",
			"username": username or "",
			"password": password or "",
			"nodes": nodes_v,
			"visible_on_device_panel": bool(visible_on_device_panel),
		}
	)
	opc_cfg["endpoints"] = endpoints
	save_app_config(cfg)
	ui.notify("OPC UA endpoint added.", type="positive")
	dlg.close()

	wid = generate_wrapper_id(OPCUA_LIST.id_prefix, name.strip())
	_render_endpoints.refresh(scroll_to=wid, highlight=wid)


def _update_endpoint(
	index: int,
	name: str,
	server_url: str,
	timeout_s: str,
	auto_connect: bool,
	security_policy: str,
	security_mode: str,
	username: str,
	password: str,
	nodes_raw: str,
	visible_on_device_panel: bool,
) -> None:
	if not name.strip() or not server_url.strip():
		ui.notify("Name and server URL are required.", type="negative")
		return
	timeout_v = _parse_float(timeout_s, "Timeout must be a number.")
	if timeout_v is None:
		return
	nodes_v = _parse_nodes(nodes_raw)
	if nodes_v is None:
		return

	cfg = get_app_config()
	opc_cfg = cfg.workers.configs.setdefault("opcua", {})
	endpoints = list(opc_cfg.get("endpoints", []))
	if index < 0 or index >= len(endpoints):
		ui.notify("OPC UA endpoint not found.", type="negative")
		return

	endpoints[index] = {
		"name": name,
		"server_url": server_url.strip(),
		"timeout_s": timeout_v,
		"auto_connect": bool(auto_connect),
		"security_policy": security_policy or "None",
		"security_mode": security_mode or "None",
		"username": username or "",
		"password": password or "",
		"nodes": nodes_v,
		"visible_on_device_panel": bool(visible_on_device_panel),
	}
	opc_cfg["endpoints"] = endpoints
	save_app_config(cfg)
	ui.notify("OPC UA endpoint updated.", type="positive")
	_render_endpoints.refresh()


def _delete_endpoint(index: int) -> None:
	cfg = get_app_config()
	opc_cfg = cfg.workers.configs.setdefault("opcua", {})
	endpoints = list(opc_cfg.get("endpoints", []))
	if index < 0 or index >= len(endpoints):
		ui.notify("OPC UA endpoint not found.", type="negative")
		return
	endpoints.pop(index)
	opc_cfg["endpoints"] = endpoints
	save_app_config(cfg)
	ui.notify("OPC UA endpoint deleted.", type="positive")
	_render_endpoints.refresh()
