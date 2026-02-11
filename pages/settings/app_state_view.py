# pages/app_state_inspector.py
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Tuple

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page


def render(container: ui.element, ctx: PageContext) -> None:
	# --- lifecycle management (same pattern as Scripts Lab / Home) ---
	page_timers: list = []

	def add_timer(*args, **kwargs):
		t = ui.timer(*args, **kwargs)
		page_timers.append(t)
		return t

	def cleanup() -> None:
		for t in page_timers:
			try:
				t.cancel()
			except Exception:
				pass
		page_timers[:] = []

	ctx.state._page_cleanup = cleanup
	ui.context.client.on_disconnect(cleanup)

	def build_content(_parent: ui.element) -> None:
		with ui.column().classes("w-full h-screen box-border gap-3 px-6 pb-6 pt-2 overflow-hidden"):
			ui.label("AppState Inspector").classes("text-xl font-semibold")

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
					with ui.row().classes("w-full justify-end"):
						ui.button("Close", on_click=dlg.close).props("outline")

			def open_details(row: Dict[str, Any]) -> None:
				try:
					key = row.get("key", "")
					dlg_title.set_text("Details: %s" % key)
					raw = _get_state_value(ctx.state, key)
					code.set_content(_safe_format_value(raw, max_len=20000))
					dlg.open()
				except Exception:
					# Keep it quiet; inspector must not crash the UI
					pass

			table.on("rowClick", lambda e: open_details(e.args))

			last_snapshot: Dict[str, str] = {}

			def refresh_table(force: bool = False) -> None:
				# build rows
				items = _extract_state_items(ctx.state)

				flt = (filter_input.value or "").strip().lower()
				rows: List[Dict[str, str]] = []
				snapshot: Dict[str, str] = {}

				for k, v in items:
					if flt and flt not in k.lower():
						continue
					tname = type(v).__name__
					vstr = _safe_format_value(v)
					rows.append({"key": k, "type": tname, "value": vstr})
					snapshot[k] = "%s|%s" % (tname, vstr)

				rows.sort(key=lambda r: r["key"])

				# update only if changed (or forced) to reduce UI churn
				if (not force) and snapshot == last_snapshot:
					return

				last_snapshot.clear()
				last_snapshot.update(snapshot)

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

	build_page(ctx, container, title="AppState Inspector", content=build_content, show_action_bar=False)


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
