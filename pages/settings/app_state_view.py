# pages/app_state_inspector.py
from __future__ import annotations

import json
import time
from decimal import Decimal
import ast
from typing import Any, Dict, List, Tuple

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page
from services.worker_topics import WorkerTopics


def render(container: ui.element, ctx: PageContext) -> None:
	# --- lifecycle management (same pattern as Scripts Lab / Home) ---
	page_timers: list = []
	page_subs: list = []

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		for sub in page_subs:
			try:
				sub.close()
			except Exception:
				pass
		page_subs[:] = []

		for t in page_timers:
			try:
				t.cancel()
			except Exception:
				pass
		page_timers[:] = []

	ctx.state._page_cleanup = cleanup
	ui.context.client.on_disconnect(cleanup)

	def build_content(_parent: ui.element) -> None:
		with ui.column().classes("w-full box-border gap-3 px-2 pb-2 pt-1"):
			with ui.row().classes("w-full items-center gap-3"):
				filter_input = ui.input("Filter (key contains...)").classes("w-[380px]")
				refresh_ms_input = ui.number("Refresh (ms)", value=300, min=100, max=5000, step=50).classes("w-[180px]")
				last_update_label = ui.label("Last update: -").classes("text-sm text-gray-400")

				ui.button("Refresh now", on_click=lambda: refresh_table(force=True)).props("outline")

			columns = [
				{"name": "key", "label": "Key", "field": "key", "align": "left", "sortable": True},
				{"name": "type", "label": "Type", "field": "type", "align": "left", "sortable": True},
				{"name": "value", "label": "Value", "field": "value", "align": "left"},
			]

			table = ui.table(
				columns=columns,
				rows=[],
				row_key="key",
				pagination={"rowsPerPage": 50},
			).classes("w-full flex-1")

			# Details dialog (click a row to inspect full value)
			dlg = ui.dialog()
			with dlg:
				with ui.card().classes("w-[900px] max-w-[95vw]"):
					dlg_title = ui.label("Details").classes("text-lg font-semibold")
					code = ui.code("").classes("w-full max-h-[70vh] overflow-auto")
					with ui.row().classes("w-full justify-end gap-2"):
						ui.button("Edit value", on_click=lambda: open_edit_dialog()).props("color=primary")
						ui.button("Close", on_click=dlg.close).props("outline")

			selected_key: Dict[str, str] = {"key": ""}

			edit_dlg = ui.dialog()
			with edit_dlg:
				with ui.card().classes("w-[900px] max-w-[95vw]"):
					edit_title = ui.label("Edit value").classes("text-lg font-semibold")
					edit_hint = ui.label("").classes("text-sm text-gray-500")
					edit_input = ui.textarea(label="New value").props("autogrow outlined").classes("w-full")
					with ui.row().classes("w-full justify-end gap-2"):
						ui.button("Cancel", on_click=edit_dlg.close).props("outline")
						ui.button("Save", on_click=lambda: save_edit()).props("color=primary")

			def _extract_clicked_row(args: Any) -> Dict[str, Any] | None:
				try:
					if isinstance(args, dict):
						return args
					if isinstance(args, (list, tuple)):
						# NiceGUI/Quasar often sends [evt, row, index]
						for item in args:
							if isinstance(item, dict) and "key" in item:
								return item
					return None
				except Exception:
					return None

			def open_details(row: Dict[str, Any]) -> None:
				try:
					key = row.get("key", "")
					selected_key["key"] = key
					dlg_title.set_text("Details: %s" % key)
					raw = last_raw_by_key.get(key, _get_state_value(ctx.state, key))
					code.set_content(_safe_format_value(raw, max_len=20000))
					dlg.open()
				except Exception:
					ui.notify("Cannot open details for selected row.", type="negative")

			def open_edit_dialog() -> None:
				try:
					key = selected_key.get("key", "")
					if not key:
						ui.notify("Select a row first.", type="warning")
						return
					raw = _get_state_value(ctx.state, key)
					edit_title.set_text("Edit: %s" % key)
					edit_hint.set_text("Type follows current value type: %s" % type(raw).__name__)
					edit_input.value = _safe_format_value(raw, max_len=20000)
					edit_dlg.open()
				except Exception as ex:
					ui.notify("Cannot open editor: %s" % ex, type="negative")

			def save_edit() -> None:
				key = selected_key.get("key", "")
				if not key:
					ui.notify("Select a row first.", type="warning")
					return
				if row_scope.get(key) != "app_state":
					ui.notify("Worker/device values are read-only here.", type="warning")
					return
				current = _get_state_value(ctx.state, key)
				text = str(edit_input.value or "")
				try:
					new_value = _coerce_from_text(text, current)
					_set_state_value(ctx.state, key, new_value)
					edit_dlg.close()
					dlg.close()
					refresh_table(force=True)
					ui.notify("Updated '%s'" % key, type="positive")
				except Exception as ex:
					ui.notify("Update failed: %s" % ex, type="negative")

			def on_row_click(e: Any) -> None:
				row = _extract_clicked_row(getattr(e, "args", None))
				if row is None:
					ui.notify("Row click payload not recognized.", type="warning")
					return
				open_details(row)

			table.on("rowClick", on_row_click)

			last_snapshot: Dict[str, str] = {}
			last_raw_by_key: Dict[str, Any] = {}
			row_scope: Dict[str, str] = {}
			worker_values: Dict[str, Any] = {}

			sub_values = None
			try:
				if ctx.worker_bus is not None:
					sub_values = ctx.worker_bus.subscribe(WorkerTopics.VALUE_CHANGED)
					page_subs.append(sub_values)
			except Exception:
				sub_values = None

			def _drain_worker_values() -> None:
				if sub_values is None:
					return
				while True:
					try:
						msg = sub_values.queue.get_nowait()
					except Exception:
						break
					payload = getattr(msg, "payload", None) or {}
					k = str(payload.get("key") or "")
					if not k:
						continue
					full_key = f"{str(getattr(msg, 'source', '') or '')}/{str(getattr(msg, 'source_id', '') or '')}/{k}"
					worker_values[full_key] = payload.get("value")

			def refresh_table(force: bool = False) -> None:
				_drain_worker_values()

				# build rows
				items = _extract_state_items(ctx.state)

				flt = (filter_input.value or "").strip().lower()
				rows: List[Dict[str, str]] = []
				snapshot: Dict[str, str] = {}
				raw_by_key: Dict[str, Any] = {}
				scope_by_key: Dict[str, str] = {}

				for k, v in items:
					if flt and flt not in k.lower():
						continue
					tname = type(v).__name__
					vstr = _safe_format_value(v)
					rows.append({"key": k, "type": tname, "value": vstr})
					snapshot[k] = "%s|%s" % (tname, vstr)
					raw_by_key[k] = v
					scope_by_key[k] = "app_state"

				for k, v in list(worker_values.items()):
					if flt and flt not in k.lower():
						continue
					tname = type(v).__name__
					vstr = _safe_format_value(v)
					rows.append({"key": k, "type": tname, "value": vstr})
					snapshot[k] = "%s|%s" % (tname, vstr)
					raw_by_key[k] = v
					scope_by_key[k] = "worker"

				rows.sort(key=lambda r: r["key"])

				# update only if changed (or forced) to reduce UI churn
				if (not force) and snapshot == last_snapshot:
					return

				last_snapshot.clear()
				last_snapshot.update(snapshot)
				last_raw_by_key.clear()
				last_raw_by_key.update(raw_by_key)
				row_scope.clear()
				row_scope.update(scope_by_key)

				table.rows = rows
				table.update()

				last_update_label.set_text("Last update: %s" % time.strftime("%H:%M:%S"))

			# timer tick: re-read refresh interval each time (so changing the number applies immediately)
			def tick() -> None:
				try:
					# dynamic interval control: emulate variable refresh rate by skipping ticks
					# (NiceGUI timer interval is fixed, so we do a cheap gate here)
					now = time.time()
					if not hasattr(tick, "_next_ts"):
						tick._next_ts = 0.0  # type: ignore[attr-defined]
					interval_s = max(0.1, float((refresh_ms_input.value or 300)) / 1000.0)
					if now < tick._next_ts:  # type: ignore[attr-defined]
						return
					tick._next_ts = now + interval_s  # type: ignore[attr-defined]
				except Exception:
					# fallback interval
					pass

				refresh_table(force=False)

			# initial
			refresh_table(force=True)
			add_timer(0.05, tick)

	build_page(ctx, container, title=None, content=build_content, show_action_bar=False)


def _extract_state_items(state: Any) -> List[Tuple[str, Any]]:
	"""
	Return a stable list of (key, value) pairs from ctx.state.

	Strategy:
	1) If state provides to_dict()/as_dict()/dict(), use it.
	2) Else use __dict__ (common for dynamic attribute containers).
	3) Else fallback to dir() and getattr() for non-callable public attributes.
	"""
	# 1) dict-style
	for fn_name in ("to_dict", "as_dict", "dict"):
		try:
			fn = getattr(state, fn_name, None)
			if callable(fn):
				data = fn()
				if isinstance(data, dict):
					return _filter_public_items(data.items())
		except Exception:
			pass

	# 2) __dict__
	try:
		if hasattr(state, "__dict__") and isinstance(state.__dict__, dict):
			return _filter_public_items(state.__dict__.items())
	except Exception:
		pass

	# 3) dir() fallback
	items: List[Tuple[str, Any]] = []
	try:
		for name in dir(state):
			if not name or name.startswith("_"):
				continue
			try:
				val = getattr(state, name)
			except Exception:
				continue
			if callable(val):
				continue
			items.append((name, val))
	except Exception:
		pass

	return items


def _filter_public_items(items) -> List[Tuple[str, Any]]:
	out: List[Tuple[str, Any]] = []
	try:
		for k, v in items:
			if not isinstance(k, str):
				continue
			if k.startswith("_"):
				continue
			if callable(v):
				continue
			out.append((k, v))
	except Exception:
		pass
	return out


def _get_state_value(state: Any, key: str) -> Any:
	# Try attribute first
	try:
		if hasattr(state, key):
			return getattr(state, key)
	except Exception:
		pass
	# Try dict-like
	try:
		if isinstance(state, dict):
			return state.get(key)
	except Exception:
		pass
	# Try __dict__
	try:
		if hasattr(state, "__dict__") and isinstance(state.__dict__, dict):
			return state.__dict__.get(key)
	except Exception:
		pass
	return None


def _set_state_value(state: Any, key: str, value: Any) -> None:
	# Prefer attribute assignment to keep dataclass behavior.
	try:
		if hasattr(state, key):
			setattr(state, key, value)
			return
	except Exception:
		pass
	try:
		if isinstance(state, dict):
			state[key] = value
			return
	except Exception:
		pass
	try:
		if hasattr(state, "__dict__") and isinstance(state.__dict__, dict):
			state.__dict__[key] = value
			return
	except Exception:
		pass
	raise ValueError("Key '%s' is not writable" % key)


def _coerce_from_text(text: str, current_value: Any) -> Any:
	s = text.strip()
	t = type(current_value)

	if current_value is None:
		if s.lower() in ("none", "null", ""):
			return None
		try:
			return ast.literal_eval(s)
		except Exception:
			return s

	if t is str:
		return text
	if t is bool:
		v = s.lower()
		if v in ("true", "1", "yes", "on"):
			return True
		if v in ("false", "0", "no", "off"):
			return False
		raise ValueError("Boolean expected: true/false")
	if t is int:
		return int(s)
	if t is float:
		return float(s)
	if isinstance(current_value, Decimal):
		return Decimal(s)
	if isinstance(current_value, (list, dict, tuple, set)):
		try:
			parsed = json.loads(s)
		except Exception:
			parsed = ast.literal_eval(s)
		if isinstance(current_value, list):
			if not isinstance(parsed, list):
				raise ValueError("List expected")
			return parsed
		if isinstance(current_value, dict):
			if not isinstance(parsed, dict):
				raise ValueError("Dict expected")
			return parsed
		if isinstance(current_value, tuple):
			if not isinstance(parsed, (list, tuple)):
				raise ValueError("Tuple/list expected")
			return tuple(parsed)
		if isinstance(current_value, set):
			if not isinstance(parsed, (list, tuple, set)):
				raise ValueError("Set/list expected")
			return set(parsed)

	# fallback for custom values: try python literal, then raw string
	try:
		return ast.literal_eval(s)
	except Exception:
		return text


def _safe_format_value(value: Any, max_depth: int = 6, max_len: int = 4000) -> str:
	"""
	Format value safely:
	- avoids recursion loops
	- tries JSON for dict/list
	- truncates long output
	"""
	seen = set()

	def _walk(v: Any, depth: int) -> Any:
		if depth <= 0:
			return "<max_depth>"
		vid = id(v)
		if vid in seen:
			return "<recursion>"
		seen.add(vid)

		# primitives
		if v is None or isinstance(v, (bool, int, float, str)):
			return v

		# bytes
		if isinstance(v, (bytes, bytearray)):
			try:
				return "<bytes len=%s>" % len(v)
			except Exception:
				return "<bytes>"

		# containers
		if isinstance(v, dict):
			out = {}
			for kk, vv in list(v.items())[:200]:
				try:
					out[str(kk)] = _walk(vv, depth - 1)
				except Exception:
					out[str(kk)] = "<unrepr>"
			return out

		if isinstance(v, (list, tuple, set)):
			out_list = []
			for item in list(v)[:200]:
				try:
					out_list.append(_walk(item, depth - 1))
				except Exception:
					out_list.append("<unrepr>")
			return out_list

		# fallback: repr
		try:
			return repr(v)
		except Exception:
			return "<unrepresentable>"

	try:
		normalized = _walk(value, max_depth)
		if isinstance(normalized, (dict, list)):
			s = json.dumps(normalized, indent=2, sort_keys=True)
		else:
			s = str(normalized)
	except Exception:
		try:
			s = repr(value)
		except Exception:
			s = "<unrepresentable>"

	if len(s) > max_len:
		return s[:max_len] + "\n<truncated>"
	return s
