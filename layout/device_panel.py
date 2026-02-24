from __future__ import annotations

import queue
import time
from typing import Any

from nicegui import ui

from layout.context import PageContext
from services.app_config import (
	get_app_config,
	get_com_device_entries,
	get_itac_endpoints,
	get_opcua_endpoints,
	get_rest_api_endpoints,
	get_tcp_client_entries,
	get_twincat_plc_endpoints,
)
from services.worker_commands import (
	ComDeviceCommands,
	ItacCommands,
	OpcUaCommands,
	RestApiCommands,
	TcpClientCommands,
	TwinCatCommands,
)
from services.worker_topics import WorkerTopics


def build_device_panel(ctx: PageContext) -> ui.right_drawer:
	cfg = get_app_config()
	visible_default = bool(getattr(cfg.ui.navigation, "show_device_panel", False))
	if visible_default and ctx.state is not None:
		try:
			setattr(ctx.state, "operator_show_device_panel", True)
		except Exception:
			pass

	with ui.right_drawer(value=visible_default, bordered=True).props("width=340") as drawer:
		ctx.right_drawer = drawer
		with ui.column().classes("w-full gap-2 p-2"):
			ui.label("Device Panel").classes("text-base font-semibold")
			body = ui.column().classes("w-full gap-2")

	with ui.dialog().props("persistent") as details_dialog, ui.card().classes("min-w-[360px] max-w-[520px] p-4"):
		details_item_ref: dict[str, Any] = {}

		def _reset_current_details_item() -> None:
			if details_item_ref:
				_send_reset(dict(details_item_ref))

		ui.label("Device Details").classes("text-base font-semibold")
		with ui.column().classes("w-full gap-1 text-sm"):
			details_name = ui.label("Name: -")
			details_source = ui.label("Source: -")
			details_source_id = ui.label("Source ID: -")
			details_worker = ui.label("Worker: -")
			details_connected = ui.label("Connected: No")
			details_state = ui.label("State: -")
			details_status = ui.label("Status: -")
			details_error_title = ui.label("Last Error").classes("font-semibold hidden")
			details_error_text = ui.label("").classes("whitespace-pre-wrap text-red-700 hidden")
		with ui.row().classes("w-full justify-end gap-2 pt-2"):
			details_show_vars_btn = ui.button("Show details", on_click=lambda: _open_vars(dict(details_item_ref))).props("color=primary").on("click.stop")
			details_reset_btn = ui.button("Reset", on_click=_reset_current_details_item).props("color=warning").on("click.stop")
			ui.button("Close", on_click=details_dialog.close).props("flat")

	with ui.dialog().props("maximized") as vars_dialog:
		with ui.card().classes("w-full h-full p-0"):
			with ui.row().classes("w-full items-center px-4 py-3 bg-gray-100 dark:bg-gray-900"):
				with ui.column().classes("gap-0"):
					vars_title = ui.label("Device Variables").classes("text-lg font-semibold")
					vars_subtitle = ui.label("-").classes("text-xs text-gray-600")
				ui.space()
				ui.button("Close", on_click=vars_dialog.close).props("flat")
			with ui.row().classes("w-full items-center gap-2 px-4 py-2 border-b"):
				vars_filter = ui.input("Filter").props("dense clearable").classes("w-full")
			with ui.scroll_area().classes("w-full h-[calc(100vh-140px)]"):
				vars_body = ui.column().classes("w-full gap-2 p-4")

	vars_item_ref: dict[str, Any] = {}
	vars_row_refs: dict[str, dict[str, Any]] = {}
	vars_render_signature: tuple[Any, ...] = tuple()
	call_history_by_key: dict[str, list[dict[str, Any]]] = {}

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
		return f"{text[:max_len - 3]}..."

	def _safe_json(value: Any) -> str:
		if value is None:
			return "None"
		if isinstance(value, bool):
			return "True" if value else "False"
		if isinstance(value, (int, float)):
			return str(value)
		return str(value)

	def _infer_editor_kind(plc_type: str, value: Any) -> str:
		t = str(plc_type or "").strip().upper()
		if t.startswith("BOOL"):
			return "bool"
		if t in ("SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT", "WORD", "DWORD", "LWORD", "BYTE"):
			return "int"
		if t in ("REAL", "LREAL"):
			return "float"
		if t.startswith("STRING") or t.startswith("WSTRING"):
			return "text"
		if isinstance(value, bool):
			return "bool"
		if isinstance(value, int) and not isinstance(value, bool):
			return "int"
		if isinstance(value, float):
			return "float"
		return "text"

	def _coerce_twincat_value(value: Any, plc_type: str) -> Any:
		t = str(plc_type or "").strip().upper()
		if t.startswith("BOOL"):
			return bool(value)
		if t in ("SINT", "USINT", "INT", "UINT", "DINT", "UDINT", "LINT", "ULINT", "WORD", "DWORD", "LWORD", "BYTE"):
			return int(value)
		if t in ("REAL", "LREAL"):
			return float(value)
		if t.startswith("STRING") or t.startswith("WSTRING"):
			return "" if value is None else str(value)
		return value

	def _coerce_by_editor(value: Any, kind: str) -> Any:
		k = str(kind or "text")
		if k == "bool":
			return bool(value)
		if k == "int":
			return int(value)
		if k == "float":
			return float(value)
		return "" if value is None else str(value)

	def _runtime_key(item: dict[str, Any]) -> str:
		return f'{str(item.get("source") or "")}:{str(item.get("source_id") or "")}'

	def _history_key(source: str, source_id: str) -> str:
		return f"{source}:{source_id}"

	def _truncate_text(value: Any, max_len: int = 200) -> str:
		text = str(value or "")
		if len(text) <= max_len:
			return text
		return f"{text[:max_len - 3]}..."

	def _summarize_rest_call(value: Any) -> tuple[str, str]:
		if not isinstance(value, dict):
			return ("REST call", _truncate_text(value, 220))
		method = str(value.get("method") or "HTTP").upper()
		status = str(value.get("status") or "-")
		ok = bool(value.get("ok", False))
		url = _truncate_text(value.get("url") or "", 120)
		elapsed = value.get("elapsed_ms")
		title = f"{method} {status} {'OK' if ok else 'ERR'}"
		detail = f"{url}"
		if elapsed is not None:
			detail = f"{detail} | {elapsed} ms"
		return (title, detail)

	def _summarize_itac_call(key: str, value: Any) -> tuple[str, str]:
		parts = str(key or "").split(".")
		action = parts[2] if len(parts) > 2 else "call"
		title = f"iTAC {action}"
		if isinstance(value, dict):
			rc = None
			for candidate in ("returnCode", "return_code", "resultCode", "result_code", "errorCode", "error_code", "code"):
				if candidate in value:
					rc = value.get(candidate)
					break
			if rc is None and isinstance(value.get("result"), dict):
				for candidate in ("returnCode", "return_code", "resultCode", "result_code", "errorCode", "error_code", "code"):
					if candidate in value.get("result", {}):
						rc = value.get("result", {}).get(candidate)
						break
			detail = _truncate_text(value.get("message") or value.get("error") or value.get("description") or "", 200)
			if rc is not None:
				title = f"{title} rc={rc}"
			if detail:
				return (title, detail)
			return (title, _truncate_text(value, 200))
		return (title, _truncate_text(value, 200))

	def _push_call_entry(source: str, source_id: str, entry: dict[str, Any]) -> None:
		k = _history_key(source, source_id)
		items = list(call_history_by_key.get(k, []))
		items.append(dict(entry))
		if len(items) > 10:
			items = items[-10:]
		call_history_by_key[k] = items

	def _push_call_from_value(source: str, source_id: str, key: str, value: Any) -> None:
		now_ts = time.time()
		if source == "tcp_client":
			if key != "message":
				return
			size = 0
			if isinstance(value, (bytes, bytearray)):
				size = len(value)
				try:
					preview = bytes(value).decode("utf-8", "replace")
				except Exception:
					preview = str(value)
			else:
				preview = str(value)
				size = len(preview.encode("utf-8", "ignore"))
			_push_call_entry(source, source_id, {
				"ts": now_ts,
				"title": f"RX message ({size} B)",
				"detail": _truncate_text(preview, 220),
			})
			return

		if source == "rest_api":
			if not str(key).startswith(f"rest.{source_id}.result."):
				return
			title, detail = _summarize_rest_call(value)
			_push_call_entry(source, source_id, {"ts": now_ts, "title": title, "detail": detail})
			return

		if source == "itac":
			if not str(key).startswith(f"itac.{source_id}."):
				return
			title, detail = _summarize_itac_call(key, value)
			_push_call_entry(source, source_id, {"ts": now_ts, "title": title, "detail": detail})

	def _get_call_history(item: dict[str, Any]) -> list[dict[str, Any]]:
		source = str(item.get("source") or "")
		source_id = str(item.get("source_id") or "")
		if source not in ("tcp_client", "rest_api", "itac"):
			return []
		return list(call_history_by_key.get(_history_key(source, source_id), []))

	def _has_details_content(item: dict[str, Any]) -> bool:
		if _build_var_specs(item):
			return True
		if _get_call_history(item):
			return True
		return False

	def _build_var_specs(item: dict[str, Any]) -> list[dict[str, Any]]:
		source = str(item.get("source") or "")
		source_id = str(item.get("source_id") or "")
		cfg_local = get_app_config()
		specs: list[dict[str, Any]] = []

		if source == "twincat":
			for endpoint in get_twincat_plc_endpoints(cfg_local):
				if str(endpoint.client_id) != source_id:
					continue
				for sub in endpoint.subscriptions or []:
					if not isinstance(sub, dict):
						continue
					name = str(sub.get("name") or "").strip()
					if not name:
						continue
					alias = str(sub.get("alias") or "").strip()
					plc_type = str(sub.get("plc_type") or "")
					string_len = int(sub.get("string_len", 80) or 80)
					key = alias or name
					specs.append({
						"id": f"twincat:{source_id}:{key}",
						"label": key,
						"detail": f"type={plc_type}" if plc_type else "",
						"key": key,
						"symbol_name": name,
						"editor": _infer_editor_kind(plc_type, None),
						"plc_type": plc_type,
						"string_len": string_len,
						"write_mode": "twincat",
						"write_name": key,
					})
		elif source == "opcua":
			for endpoint in get_opcua_endpoints(cfg_local):
				if str(endpoint.name) != source_id:
					continue
				for node in endpoint.nodes or []:
					if not isinstance(node, dict):
						continue
					node_id = str(node.get("node_id") or "").strip()
					if not node_id:
						continue
					alias = str(node.get("alias") or "").strip() or node_id
					specs.append({
						"id": f"opcua:{source_id}:{alias}",
						"label": alias,
						"detail": node_id,
						"key": alias,
						"editor": "text",
						"write_mode": "opcua",
						"node_id": node_id,
					})

		if source in ("twincat", "opcua"):
			rt_values = runtime_values_by_key.get(_runtime_key(item), {})
			known_keys = {str(s.get("key") or "") for s in specs}
			if source == "twincat":
				# Worker publishes alias key and full symbol name for compatibility.
				# Hide runtime duplicates when they refer to configured TwinCAT symbols.
				twincat_symbol_names = {str(s.get("symbol_name") or "") for s in specs}
				known_keys = known_keys.union(twincat_symbol_names)
			for key in sorted(rt_values.keys()):
				k = str(key or "")
				if not k or k in known_keys:
					continue
				val = rt_values.get(k)
				specs.append({
					"id": f"runtime:{source}:{source_id}:{k}",
					"label": k,
					"detail": "discovered runtime value",
					"key": k,
					"editor": _infer_editor_kind("", val),
					"write_mode": "none",
				})

		return specs

	def _vars_signature(item: dict[str, Any]) -> tuple[Any, ...]:
		rt = runtime_values_by_key.get(_runtime_key(item), {})
		visible_filter = str(vars_filter.value or "").strip().lower()
		specs = _build_var_specs(item)
		rows = []
		for spec in specs:
			label = str(spec.get("label") or "")
			detail = str(spec.get("detail") or "")
			if visible_filter and visible_filter not in label.lower() and visible_filter not in detail.lower():
				continue
			rows.append((label, detail, str(spec.get("key") or ""), spec.get("write_mode"), str(type(rt.get(spec.get("key"))).__name__)))
		history_rows = []
		for entry in _get_call_history(item):
			title = str(entry.get("title") or "")
			detail = str(entry.get("detail") or "")
			if visible_filter and visible_filter not in title.lower() and visible_filter not in detail.lower():
				continue
			history_rows.append((title, detail, float(entry.get("ts") or 0.0)))
		return (tuple(rows), tuple(history_rows))

	def _write_var(item: dict[str, Any], spec: dict[str, Any], editor: Any) -> None:
		source = str(item.get("source") or "")
		source_id = str(item.get("source_id") or "")
		if not source or not source_id:
			ui.notify("Write failed: missing device info", color="negative")
			return

		try:
			raw_value = getattr(editor, "value", None)
		except Exception:
			raw_value = None

		mode = str(spec.get("write_mode") or "none")
		if mode == "twincat":
			h = ctx.workers.get("twincat") if ctx.workers else None
			if h is None:
				ui.notify("Write failed: worker 'twincat' unavailable", color="negative")
				return
			plc_type = str(spec.get("plc_type") or "")
			try:
				value = _coerce_twincat_value(raw_value, plc_type)
			except Exception as ex:
				ui.notify(f"Invalid value: {ex}", color="warning")
				return
			h.send(
				TwinCatCommands.WRITE,
				client_id=source_id,
				name=str(spec.get("write_name") or spec.get("key") or ""),
				value=value,
				plc_type=plc_type,
				string_len=int(spec.get("string_len", 80) or 80),
			)
			ui.notify(f"Write requested: {spec.get('label')}", color="info")
			return

		if mode == "opcua":
			h = ctx.workers.get("opcua") if ctx.workers else None
			if h is None:
				ui.notify("Write failed: worker 'opcua' unavailable", color="negative")
				return
			try:
				value = _coerce_by_editor(raw_value, str(spec.get("editor") or "text"))
			except Exception as ex:
				ui.notify(f"Invalid value: {ex}", color="warning")
				return
			h.send(
				OpcUaCommands.WRITE,
				name=source_id,
				node_id=str(spec.get("node_id") or ""),
				value=value,
			)
			ui.notify(f"Write requested: {spec.get('label')}", color="info")
			return

		ui.notify("Write not supported for this variable", color="warning")

	def _render_vars(item: dict[str, Any]) -> None:
		nonlocal vars_render_signature
		visible_filter = str(vars_filter.value or "").strip().lower()
		rt_values = runtime_values_by_key.get(_runtime_key(item), {})
		specs = _build_var_specs(item)
		call_history = _get_call_history(item)

		vars_body.clear()
		vars_row_refs.clear()
		with vars_body:
			if not specs and not call_history:
				ui.label("No details available for this device").classes("text-sm text-gray-500")
				vars_render_signature = tuple()
				return

			shown_vars = 0
			if specs:
				ui.label("Variables").classes("text-sm font-semibold text-gray-700")
				with ui.row().classes("w-full items-center gap-2 px-2 py-1 bg-gray-100 rounded text-[11px] font-semibold text-gray-700"):
					ui.label("Key").classes("flex-[2]")
					ui.label("Symbol").classes("flex-[3]")
					ui.label("Type").classes("w-24 text-right")
					ui.label("Current").classes("w-52 text-right")
					ui.label("Edit").classes("w-56")
					ui.label("Write").classes("w-20 text-right")
			for spec in specs:
				label = str(spec.get("label") or "")
				detail = str(spec.get("detail") or "")
				if visible_filter and visible_filter not in label.lower() and visible_filter not in detail.lower():
					continue
				shown_vars += 1
				key = str(spec.get("key") or "")
				symbol_name = str(spec.get("symbol_name") or "")
				current_value = rt_values.get(key)
				if current_value is None and symbol_name:
					current_value = rt_values.get(symbol_name)
				editor_kind = _infer_editor_kind(str(spec.get("plc_type") or ""), current_value)
				spec["editor"] = editor_kind
				plc_type = str(spec.get("plc_type") or "-")

				with ui.row().classes("w-full items-center gap-2 px-2 py-2 border-b"):
					with ui.column().classes("flex-[2] gap-0"):
						ui.label(label).classes("text-sm font-semibold")
					with ui.column().classes("flex-[3] gap-0"):
						ui.label(symbol_name or "-").classes("text-xs text-gray-600 break-all")
					ui.label(plc_type).classes("w-24 text-xs text-gray-700 text-right")
					with ui.row().classes("w-52 justify-end"):
						value_label = ui.label(_safe_json(current_value)).classes(
							"text-base font-mono font-bold px-4 py-2 rounded-lg border-2 border-blue-500 bg-blue-100 text-blue-950 shadow-sm"
						)
					with ui.row().classes("w-56"):
						editor: Any
						if editor_kind == "bool":
							editor = ui.switch(value=bool(current_value)).props("dense")
						elif editor_kind == "int":
							editor = ui.number(value=(int(current_value) if isinstance(current_value, (int, float)) and not isinstance(current_value, bool) else 0), format="%.0f").props("dense outlined")
						elif editor_kind == "float":
							editor = ui.number(value=(float(current_value) if isinstance(current_value, (int, float)) and not isinstance(current_value, bool) else 0.0), format="%.6f").props("dense outlined")
						else:
							editor = ui.input(value=("" if current_value is None else str(current_value))).props("dense outlined")
							editor.classes("w-full")
					with ui.row().classes("w-20 justify-end"):
						write_btn = ui.button("Write", on_click=lambda _e=None, i=dict(item), s=dict(spec), ed=editor: _write_var(i, s, ed)).props("color=primary")
						if str(spec.get("write_mode") or "none") == "none":
							write_btn.disable()
							with write_btn:
								ui.tooltip("Read-only")

				vars_row_refs[str(spec.get("id") or key)] = {
					"spec": dict(spec),
					"value_label": value_label,
				}

			if specs and shown_vars == 0:
				ui.label("No variables matching the filter").classes("text-sm text-gray-500")

			shown_calls = 0
			if call_history:
				if specs and shown_vars > 0:
					ui.separator()
				ui.label("Last 10 calls").classes("text-sm font-semibold text-gray-700")
				for entry in reversed(call_history):
					title = str(entry.get("title") or "")
					detail = str(entry.get("detail") or "")
					if visible_filter and visible_filter not in title.lower() and visible_filter not in detail.lower():
						continue
					shown_calls += 1
					with ui.card().classes("w-full p-3"):
						with ui.column().classes("gap-0"):
							ui.label(title).classes("text-sm font-semibold")
							if detail:
								ui.label(detail).classes("text-xs text-gray-600 whitespace-pre-wrap")
							ts = float(entry.get("ts") or 0.0)
							if ts > 0.0:
								ui.label(time.strftime("%H:%M:%S", time.localtime(ts))).classes("text-[11px] text-gray-500")
			if call_history and shown_calls == 0:
				ui.label("No calls matching the filter").classes("text-sm text-gray-500")

		vars_render_signature = _vars_signature(item)

	def _refresh_vars_if_open() -> None:
		if not bool(getattr(vars_dialog, "value", False)):
			return
		if not vars_item_ref:
			return

		item = dict(vars_item_ref)
		next_sig = _vars_signature(item)
		nonlocal vars_render_signature
		if next_sig != vars_render_signature:
			_render_vars(item)
			return

		rt_values = runtime_values_by_key.get(_runtime_key(item), {})
		for ref in vars_row_refs.values():
			spec = ref.get("spec") if isinstance(ref, dict) else None
			if not isinstance(spec, dict):
				continue
			key = str(spec.get("key") or "")
			value_label = ref.get("value_label")
			if value_label is None:
				continue
			symbol_name = str(spec.get("symbol_name") or "")
			current = rt_values.get(key)
			if current is None and symbol_name:
				current = rt_values.get(symbol_name)
			try:
				value_label.set_text(_safe_json(current))
			except Exception:
				pass

	def _open_vars(item: dict[str, Any]) -> None:
		vars_item_ref.clear()
		vars_item_ref.update(dict(item))
		vars_title.set_text(f"Device Variables - {str(item.get('name') or '-')}")
		vars_subtitle.set_text(f"Source: {str(item.get('source') or '-')} | ID: {str(item.get('source_id') or '-')}")
		_render_vars(dict(item))
		vars_dialog.open()

	vars_filter.on("update:model-value", lambda _e: _refresh_vars_if_open())

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
		details_name.set_text(f'Name: {str(item.get("name") or "-")}')
		details_source.set_text(f'Source: {str(item.get("source") or "-")}')
		details_source_id.set_text(f'Source ID: {str(item.get("source_id") or "-")}')
		details_worker.set_text(f'Worker: {str(runtime.get("worker") or str(item.get("source") or "-"))}')
		details_connected.set_text(f'Connected: {"Yes" if bool(item.get("connected", False)) else "No"}')
		details_state.set_text(f'State: {str(item.get("state") or "-")}')
		details_status.set_text(f'Status: {str(item.get("status") or "-")}')
		error_text = str(runtime.get("error") or "").strip()
		if error_text:
			details_error_title.classes(remove="hidden")
			details_error_text.classes(remove="hidden")
			details_error_text.set_text(error_text)
		else:
			details_error_title.classes(add="hidden")
			details_error_text.classes(add="hidden")
			details_error_text.set_text("")
		details_item_ref.clear()
		details_item_ref.update(dict(item))
		reset_source = str(item.get("source") or "").strip()
		reset_source_id = str(item.get("source_id") or "").strip()
		can_reset = bool(reset_source in _reset_cmd_map and reset_source_id)
		if can_reset:
			details_reset_btn.classes(remove="hidden")
		else:
			details_reset_btn.classes(add="hidden")
		if _has_details_content(item):
			details_show_vars_btn.enable()
		else:
			details_show_vars_btn.disable()
		details_dialog.open()

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
					with ui.card().classes("w-full px-2 py-1"):
						with ui.row().classes("w-full items-center gap-2"):
							ui.icon(icon_name).classes(icon_color)
							with ui.column().classes("gap-0"):
								ui.label(name).classes("text-sm font-semibold")
								ui.label(str(item.get("source") or "")).classes("text-[10px] text-gray-500")
							ui.space()
							ui.badge(_truncate_status(status)).props(f"color={state_color} text-color=white").classes("text-[10px]")
						with ui.row().classes("w-full justify-end gap-1 pb-1"):
							ui.button("Details", on_click=lambda _e=None, i=dict(item), r=dict(runtime): _open_details(i, r)).props("flat dense").on("click.stop")

		if ctx.device_panel_toggle_btn is not None:
			try:
				if drawer.value:
					ctx.device_panel_toggle_btn.props("color=primary")
				else:
					ctx.device_panel_toggle_btn.props(remove="color=primary")
			except Exception:
				pass

	timer = ui.timer(0.5, _apply)
	vars_refresh_timer = ui.timer(0.3, _refresh_vars_if_open)
	runtime_by_key: dict[str, dict[str, Any]] = {}
	runtime_values_by_key: dict[str, dict[str, Any]] = {}
	sub = ctx.worker_bus.subscribe_many([
		WorkerTopics.CLIENT_CONNECTED,
		WorkerTopics.CLIENT_DISCONNECTED,
		WorkerTopics.VALUE_CHANGED,
		WorkerTopics.ERROR,
		WorkerTopics.WRITE_ERROR,
		WorkerTopics.WRITE_FINISHED,
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

	def _set_value(source: str, source_id: str, key: str, value: Any) -> None:
		device_key = f"{source}:{source_id}"
		current_values = dict(runtime_values_by_key.get(device_key, {}))
		current_values[str(key)] = value
		runtime_values_by_key[device_key] = current_values

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
			if topic == str(WorkerTopics.WRITE_ERROR):
				err = str(payload.get("error") or "Write failed")
				_set_rt(source, source_id, state="error", status=err, error=err)
				if source in ("tcp_client", "rest_api", "itac"):
					_push_call_entry(source, source_id, {"ts": time.time(), "title": "Write error", "detail": _truncate_text(err, 220)})
				ui.notify(f"Write error ({source}:{source_id}): {err}", color="negative")
				continue
			if topic == str(WorkerTopics.WRITE_FINISHED):
				_set_rt(source, source_id, state="success", status="Write finished")
				if source == "tcp_client":
					write_key = str(payload.get("key") or "")
					if write_key:
						_push_call_entry(source, source_id, {"ts": time.time(), "title": f"TX {write_key}", "detail": "Write finished"})
				continue
			if topic != str(WorkerTopics.VALUE_CHANGED):
				continue

			key = str(payload.get("key") or "")
			value = payload.get("value")
			if key:
				_set_value(source, source_id, key, value)
				_push_call_from_value(source, source_id, key, value)

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
			vars_refresh_timer.cancel()
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
