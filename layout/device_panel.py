from __future__ import annotations

import queue
import time
from typing import Any

from nicegui import ui

from layout.context import PageContext
from services.app_config import (
	get_app_config,
	get_tcp_client_entries,
	get_com_device_entries,
	get_opcua_endpoints,
	get_itac_endpoints,
	get_rest_api_endpoints,
	get_twincat_plc_endpoints,
)
from services.worker_topics import WorkerTopics
from services.worker_commands import (
	TcpClientCommands,
	ComDeviceCommands,
	OpcUaCommands,
	ItacCommands,
	RestApiCommands,
	TwinCatCommands,
)


def build_device_panel(ctx: PageContext) -> ui.right_drawer:
	cfg = get_app_config()
	visible_default = bool(getattr(cfg.ui.navigation, "show_device_panel", False))
	if visible_default and ctx.state is not None:
		try:
			setattr(ctx.state, "operator_show_device_panel", True)
		except Exception:
			pass

	with ui.right_drawer(value=visible_default, bordered=True).props("width=300") as drawer:
		ctx.right_drawer = drawer
		with ui.column().classes("w-full gap-2 p-2"):
			ui.label("Device Panel").classes("text-base font-semibold")
			body = ui.column().classes("w-full gap-2")

	def _normalize_state(value: str) -> str:
		v = str(value or "").strip().lower()
		if v in ("success", "ok", "good", "online"):
			return "positive"
		if v in ("warn", "warning", "degraded"):
			return "warning"
		if v in ("error", "bad", "offline", "disconnected", "negative"):
			return "negative"
		return "info"

	def _truncate_status(value: str, max_len: int = 40) -> str:
		text = str(value or "").strip()
		if len(text) <= max_len:
			return text
		return f"{text[:max_len - 1]}…"


	_reset_cmd_map: dict[str, tuple[str, Any, str]] = {
		"tcp_client": ("tcp_client", TcpClientCommands.RESET, "client_id"),
		"com_device": ("com_device", ComDeviceCommands.RESET, "device_id"),
		"opcua": ("opcua", OpcUaCommands.RESET, "name"),
		"itac": ("itac", ItacCommands.RESET, "connection_id"),
		"rest_api": ("rest_api", RestApiCommands.RESET, "name"),
		"twincat": ("twincat", TwinCatCommands.RESET, "client_id"),
	}
	_reset_debounce_s = 1.2
	_last_reset_at: dict[str, float] = {}

	def _send_reset(item: dict[str, Any]) -> None:
		source = str(item.get("source") or "").strip()
		source_id = str(item.get("source_id") or "").strip()
		if not source or not source_id:
			ui.notify("Reset skipped: missing device info", color="warning")
			return
		cmd_info = _reset_cmd_map.get(source)
		if not cmd_info:
			ui.notify(f"Reset not supported for {source}", color="warning")
			return
		now = time.monotonic()
		key = f"{source}:{source_id}"
		last = float(_last_reset_at.get(key, 0.0))
		if (now - last) < _reset_debounce_s:
			return
		_last_reset_at[key] = now
		worker_name, cmd, payload_key = cmd_info
		h = ctx.workers.get(worker_name) if ctx.workers is not None else None
		if h is None:
			ui.notify(f"Reset failed: worker '{worker_name}' is not available", color="negative")
			return
		h.send(cmd, **{payload_key: source_id})
		ui.notify(f"Reset requested for {source_id}", color="info")

	def _open_details(item: dict[str, Any], runtime: dict[str, Any]) -> None:
		with ui.dialog() as dialog, ui.card().classes("min-w-[360px] max-w-[520px] p-4"):
			ui.label("Device Details").classes("text-base font-semibold")
			with ui.column().classes("w-full gap-1 text-sm"):
				ui.label(f'Name: {str(item.get("name") or "-")}')
				ui.label(f'Source: {str(item.get("source") or "-")}')
				ui.label(f'Source ID: {str(item.get("source_id") or "-")}')
				ui.label(f'Worker: {str(runtime.get("worker") or str(item.get("source") or "-"))}')
				ui.label(f'Connected: {"Yes" if bool(item.get("connected", False)) else "No"}')
				ui.label(f'State: {str(item.get("state") or "-")}')
				ui.label(f'Status: {str(item.get("status") or "-")}')
				error_text = str(runtime.get("error") or "")
				if error_text:
					ui.separator()
					ui.label("Last Error").classes("font-semibold")
					ui.label(error_text).classes("whitespace-pre-wrap text-red-700")
			with ui.row().classes("w-full justify-end gap-2 pt-2"):
				ui.button("Reset", on_click=lambda i=dict(item): _send_reset(i)).props("color=warning").on("click.stop")
				ui.button("Close", on_click=dialog.close).props("flat")
		dialog.open()

	def _apply() -> None:
		if ctx.state is None:
			return
		try:
			override = getattr(ctx.state, "operator_show_device_panel", None)
			if isinstance(override, bool):
				if override and not drawer.value:
					drawer.open()
				if (not override) and drawer.value:
					drawer.close()
		except Exception:
			pass

		items: list[dict[str, Any]] = []
		try:
			raw = getattr(ctx.state, "operator_device_panel_items", []) or []
			if isinstance(raw, list):
				for item in raw:
					if isinstance(item, dict):
						items.append(item)
		except Exception:
			pass
		cfg_local = get_app_config()

		configured: list[dict[str, Any]] = []
		for e in get_tcp_client_entries(cfg_local):
			if not bool(getattr(e, "visible_on_device_panel", False)):
				continue
			configured.append({"source": "tcp_client", "source_id": str(e.client_id), "name": str(e.client_id)})
		for e in get_com_device_entries(cfg_local):
			if not bool(getattr(e, "visible_on_device_panel", False)):
				continue
			configured.append({"source": "com_device", "source_id": str(e.device_id), "name": str(e.device_id)})
		for e in get_opcua_endpoints(cfg_local):
			if not bool(getattr(e, "visible_on_device_panel", False)):
				continue
			configured.append({"source": "opcua", "source_id": str(e.name), "name": str(e.name)})
		for e in get_itac_endpoints(cfg_local):
			if not bool(getattr(e, "visible_on_device_panel", False)):
				continue
			configured.append({"source": "itac", "source_id": str(e.name), "name": str(e.name)})
		for e in get_rest_api_endpoints(cfg_local):
			if not bool(getattr(e, "visible_on_device_panel", False)):
				continue
			configured.append({"source": "rest_api", "source_id": str(e.name), "name": str(e.name)})
		for e in get_twincat_plc_endpoints(cfg_local):
			if not bool(getattr(e, "visible_on_device_panel", False)):
				continue
			configured.append({"source": "twincat", "source_id": str(e.client_id), "name": str(e.client_id)})

		for entry in configured:
			key = f'{entry["source"]}:{entry["source_id"]}'
			rt = runtime_by_key.get(key, {})
			status_text = str(rt.get("status") or "Unknown")
			state_text = str(rt.get("state") or "info")
			connected = bool(rt.get("connected", False))
			items.append({
				"name": str(entry["name"]),
				"status": status_text,
				"state": state_text,
				"connected": connected,
				"source": str(entry["source"]),
				"source_id": str(entry["source_id"]),
			})

		body.clear()
		with body:
			if not items:
				ui.label("No devices").classes("text-xs text-gray-500")
			else:
				for item in items:
					name = str(item.get("name") or "").strip()
					if not name:
						continue
					status = str(item.get("status") or "").strip() or "-"
					state_color = _normalize_state(str(item.get("state") or "info"))
					connected = bool(item.get("connected", True))
					icon_name = "check_circle" if connected else "error"
					icon_color = "text-green-600" if connected else "text-red-600"
					item_key = f'{str(item.get("source") or "")}:{str(item.get("source_id") or "")}'
					runtime = runtime_by_key.get(item_key, {})
					with ui.card().classes("w-full px-2 py-1 cursor-pointer") as device_card:
						ui.tooltip("Click for details")
						with ui.row().classes("w-full items-center gap-2"):
							ui.icon(icon_name).classes(icon_color)
							with ui.column().classes("gap-0"):
								ui.label(name).classes("text-sm font-semibold")
								ui.label(str(item.get("source") or "")).classes("text-[10px] text-gray-500")
							ui.space()
							ui.badge(_truncate_status(status)).props(f"color={state_color} text-color=white").classes("text-[10px]")
					device_card.on("click", lambda _e, i=dict(item), r=dict(runtime): _open_details(i, r))

		if ctx.device_panel_toggle_btn is not None:
			try:
				if drawer.value:
					ctx.device_panel_toggle_btn.props("color=primary")
				else:
					ctx.device_panel_toggle_btn.props(remove="color=primary")
			except Exception:
				pass

	timer = ui.timer(0.5, _apply)
	runtime_by_key: dict[str, dict[str, Any]] = {}
	sub = ctx.worker_bus.subscribe_many([
		WorkerTopics.CLIENT_CONNECTED,
		WorkerTopics.CLIENT_DISCONNECTED,
		WorkerTopics.VALUE_CHANGED,
		WorkerTopics.ERROR,
	]) if ctx.worker_bus else None

	def _get_payload(msg: Any) -> dict[str, Any]:
		raw = getattr(msg, "payload", None)
		if not isinstance(raw, dict):
			return {}
		inner = raw.get("payload")
		if isinstance(inner, dict):
			return inner
		return raw

	def _set_rt(source: str, source_id: str, **values: Any) -> None:
		k = f"{source}:{source_id}"
		current = dict(runtime_by_key.get(k, {}))
		current.setdefault("worker", str(source))
		current.update(values)
		runtime_by_key[k] = current

	def _drain_runtime() -> None:
		if sub is None:
			return
		while True:
			try:
				msg = sub.queue.get_nowait()
			except queue.Empty:
				break
			source = str(getattr(msg, "source", "") or "")
			source_id = str(getattr(msg, "source_id", "") or "")
			if not source or not source_id:
				continue
			topic = str(getattr(msg, "topic", "") or "")
			payload = _get_payload(msg)
			if topic == str(WorkerTopics.CLIENT_CONNECTED):
				_set_rt(source, source_id, connected=True, state="success", status="Connected")
				continue
			if topic == str(WorkerTopics.CLIENT_DISCONNECTED):
				reason = str(payload.get("reason") or "Disconnected")
				_set_rt(source, source_id, connected=False, state="error", status=reason)
				continue
			if topic == str(WorkerTopics.ERROR):
				err = str(payload.get("error") or "Error")
				_set_rt(source, source_id, connected=False, state="error", status=err, error=err)
				continue
			if topic != str(WorkerTopics.VALUE_CHANGED):
				continue
			key = str(payload.get("key") or "")
			value = payload.get("value")
			if key.endswith(".connected") and isinstance(value, bool):
				_set_rt(source, source_id, connected=bool(value), state=("success" if value else "error"), status=("Connected" if value else "Disconnected"))
				continue
			if key == "status" and isinstance(value, dict):
				connected = bool(value.get("connected", False))
				error = str(value.get("error") or "")
				_set_rt(
					source,
					source_id,
					connected=connected,
					state=("success" if connected else ("error" if error else "warning")),
					status=(error if error else ("Connected" if connected else "Disconnected")),
				)
				continue
			if isinstance(value, dict) and "connected" in value:
				connected = bool(value.get("connected", False))
				_set_rt(source, source_id, connected=connected, state=("success" if connected else "warning"), status=("Connected" if connected else "Disconnected"))

	drain_timer = ui.timer(0.2, _drain_runtime)

	def _cleanup() -> None:
		try:
			timer.cancel()
		except Exception:
			pass
		try:
			drain_timer.cancel()
		except Exception:
			pass
		try:
			if sub is not None:
				sub.close()
		except Exception:
			pass

	ui.context.client.on_disconnect(_cleanup)
	_apply()
	return drawer
