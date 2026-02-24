from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Any, List, Callable, Tuple
from datetime import datetime, timezone

from nicegui import app

# ===========================
# Persistence (machine-wide)
# ===========================
_EXEC_KEY = "dummy_exec_progress"   # stored in app.storage.general


def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def load_exec_progress() -> dict[str, Any] | None:
	return app.storage.general.get(_EXEC_KEY)


def save_exec_progress(data: dict[str, Any]) -> None:
	app.storage.general[_EXEC_KEY] = data


def clear_exec_progress() -> None:
	app.storage.general.pop(_EXEC_KEY, None)

def _parse_bool(s: str) -> Optional[bool]:
	v = (s or "").strip().lower()
	if v in {"1", "true", "on", "yes"}:
		return True
	if v in {"0", "false", "off", "no"}:
		return False
	return None

# ======  Analyse test result static intern helpers  =================

def _parse_decimal(s: str) -> Optional[Decimal]:
	try:
		return Decimal((s or "").strip())
	except (InvalidOperation, ValueError):
		return None


def _parse_range_brackets(expr: str) -> Optional[tuple[Decimal, Decimal, bool, bool]]:
	"""
	Range syntax:
	  [1, 2.5]   -> inclusive both sides
	  ]0.4, 0.8] -> exclusive left, inclusive right
	  [1,2]      -> spaces optional
	Left bracket: '[' inclusive, ']' exclusive
	Right bracket: ']' inclusive, '[' exclusive
	"""
	t = (expr or "").strip()
	if len(t) < 5:
		return None

	left_br = t[0]
	right_br = t[-1]
	if left_br not in {"[", "]"} or right_br not in {"]", "["}:
		return None

	inner = t[1:-1].strip()
	if "," not in inner:
		return None
	a_str, b_str = [x.strip() for x in inner.split(",", 1)]

	a = _parse_decimal(a_str)
	b = _parse_decimal(b_str)
	if a is None or b is None:
		return None

	lo, hi = (a, b) if a <= b else (b, a)

	left_inclusive = (left_br == "[")
	right_inclusive = (right_br == "]")
	return lo, hi, left_inclusive, right_inclusive


def _in_range(val: Decimal, lo: Decimal, hi: Decimal, left_inclusive: bool, right_inclusive: bool) -> bool:
	if left_inclusive:
		if val < lo:
			return False
	else:
		if val <= lo:
			return False

	if right_inclusive:
		if val > hi:
			return False
	else:
		if val >= hi:
			return False

	return True



@dataclass
class DummyUIHandles:
	show: Callable[[], None]
	hide: Callable[[], None]
	refresh_all: Callable[[], None]
	refresh_sets: Callable[[], Any]
	refresh_left: Callable[[], Any]
	refresh_right: Callable[[], Any]
	refresh_spinner: Callable[[], Any]



# ===========================
# Execution State
# ===========================
@dataclass
class ExecutionState:
	sets: list  # List[DummySet] in your project
	selected_set_id: Optional[int] = None
	selected_dummy_id: Optional[int] = None

	# per dummy id:
	# {
	#   "state": None|True|False,
	#   "values": {inspection_id: str},  # values captured at time of completion
	# }
	dummy_results: Dict[int, dict] = field(default_factory=dict)

	# optional overall info
	started_at: Optional[str] = None
	finished_at: Optional[str] = None

	def init_defaults(self) -> None:
		"""Initialize selection and result maps (only when starting fresh)."""
		if self.sets and self.selected_set_id is None:
			self.selected_set_id = self.sets[0].id

		s = self.selected_set()
		if s and s.dummies and self.selected_dummy_id is None:
			self.selected_dummy_id = s.dummies[0].id

		# ensure every dummy has an entry
		self.ensure_dummy_result_entries()

	# ---------- navigation helpers ----------
	def selected_set(self):
		if self.selected_set_id is None:
			return None
		return next((s for s in self.sets if s.id == self.selected_set_id), None)

	def dummies(self):
		s = self.selected_set()
		return s.dummies if s else []

	def selected_dummy(self):
		if self.selected_dummy_id is None:
			return None
		return next((d for d in self.dummies() if d.id == self.selected_dummy_id), None)

	def inspections(self):
		d = self.selected_dummy()
		return d.inspections if d else []

	# ---------- result handling ----------
	def ensure_dummy_result_entries(self) -> None:
		"""Make sure dummy_results contains all dummy ids as pending entries."""
		for d in self.dummies():
			if d.id not in self.dummy_results:
				self.dummy_results[d.id] = {"state": None, "values": {}}

	def get_dummy_state(self, dummy_id: int) -> Optional[bool]:
		entry = self.dummy_results.get(dummy_id)
		if not entry:
			return None
		return entry.get("state", None)

	def set_dummy_state(
		self,
		dummy_id: int,
		state: Optional[bool],
		*,
		inspection_values: Optional[Dict[int, Any]] = None,
	) -> None:
		"""Set OK/NOK/Pending and optionally capture inspection values."""
		if dummy_id not in self.dummy_results:
			self.dummy_results[dummy_id] = {"state": None, "values": {}}

		self.dummy_results[dummy_id]["state"] = state

		if inspection_values is not None:
			# normalize to {id: str}
			self.dummy_results[dummy_id]["values"] = {int(k): str(v) for k, v in inspection_values.items()}
		self.persist()
		if self.is_finished():
			self.finish_execution()

	def capture_selected_dummy_success(self, current_values: Dict[int, Any]) -> None:
		"""Convenience for when a dummy succeeds."""
		d = self.selected_dummy()
		if not d:
			return
		self.set_dummy_state(d.id, True, inspection_values=current_values)

	def capture_selected_dummy_failure(self, current_values: Dict[int, Any] | None = None) -> None:
		"""Convenience for when a dummy fails (optional capture)."""
		d = self.selected_dummy()
		if not d:
			return
		self.set_dummy_state(d.id, False, inspection_values=current_values or {})

	def start_execution(self) -> None:
		self.cleanup()
		self.started_at = _utc_now_iso()
		self.ensure_dummy_result_entries()
		self.persist()

	def finish_execution(self) -> None:
		self.finished_at = _utc_now_iso()
		self.persist()


	def cleanup(self):
		self.started_at = None
		self.finished_at = None
		self.dummy_results = {}

	def is_finished(self) -> bool:
		"""True if all dummies have state True."""
		ds = self.dummies()
		if not ds:
			return True
		return all(self.get_dummy_state(d.id) is True for d in ds)

	# ---------- snapshot / restore (machine-wide) ----------
	def snapshot(self) -> dict[str, Any]:
		"""Serialize state for app.storage.general (no sets included)."""
		return {
			"selected_set_id": self.selected_set_id,
			"selected_dummy_id": self.selected_dummy_id,
			"dummy_results": self.dummy_results,
			"started_at": self.started_at,
			"finished_at": self.finished_at,
		}

	def persist(self) -> None:
		"""Save to global storage."""
		save_exec_progress(self.snapshot())

	def restore(self, data: dict[str, Any]) -> None:
		"""Restore from app.storage.general snapshot."""
		self.selected_set_id = data.get("selected_set_id")
		self.selected_dummy_id = data.get("selected_dummy_id")
		self.dummy_results = data.get("dummy_results", {})
		self.started_at = data.get("started_at")
		self.finished_at = data.get("finished_at")

		# validate selection against current config
		self.ensure_valid_selection()
		self.ensure_dummy_result_entries()

	def ensure_valid_selection(self) -> None:
		"""Keep selection if possible; fallback to first."""
		set_ids = [s.id for s in self.sets]
		if not set_ids:
			self.selected_set_id = None
			self.selected_dummy_id = None
			return

		if self.selected_set_id not in set_ids:
			self.selected_set_id = set_ids[0]
			self.selected_dummy_id = None

		s = self.selected_set()
		dummy_ids = [d.id for d in (s.dummies if s else [])]
		if not dummy_ids:
			self.selected_dummy_id = None
			return

		if self.selected_dummy_id not in dummy_ids:
			self.selected_dummy_id = dummy_ids[0]


	# ---- Handle dummy results -----------

	def get_dummy_state_icon(self, dummy_id: int) -> tuple[str, str]:
		"""Return (icon_name, tailwind_color_class) for the dummy state."""
		st = self.get_dummy_state(dummy_id)
		if st is True:
			return "check_circle", "text-green-600"
		if st is False:
			return "cancel", "text-red-600"
		return "help_outline", "text-gray-400"  # pending

	def remaining_dummies(self) -> list:
		return [d for d in self.dummies() if not self.get_dummy_state(d.id)]

	def _next_pending_dummy_id_after(self, dummy_id: int) -> Optional[int]:
		ds = self.dummies()
		if not ds:
			return None

		pending_ids = {d.id for d in self.remaining_dummies()}
		if not pending_ids:
			return None

		try:
			start_idx = next(i for i, d in enumerate(ds) if d.id == dummy_id)
		except StopIteration:
			start_idx = -1

		for step in range(1, len(ds) + 1):
			cand = ds[(start_idx + step) % len(ds)].id
			if cand in pending_ids:
				return cand
		return None

	def _read_current_value(self, ctx_state: Any, ins) -> str:
		prop_name = getattr(ins, "state_field_name", "") or ""
		raw = getattr(ctx_state, prop_name, "")
		return "" if raw is None else str(raw)

	def _inspection_match(self, current_val: str, ins) -> bool:
		t = (ins.type_of_value or "").strip().lower()
		expected = (ins.expected_value or "").strip()
		current = (current_val or "").strip()

		if t == "bool":
			eb = _parse_bool(expected)
			cb = _parse_bool(current)
			return (eb is not None) and (cb is not None) and (eb == cb)

		if t in {"int", "float", "number"}:
			e = _parse_decimal(expected)
			c = _parse_decimal(current)
			return (e is not None) and (c is not None) and (e == c)

		if t == "string":
			return current == expected

		if t in {"regexp", "regex"}:
			try:
				return re.search(expected, current) is not None
			except re.error:
				return False

		if t == "range":
			r = _parse_range_brackets(expected)
			c = _parse_decimal(current)
			if r is None or c is None:
				return False
			lo, hi, li, ri = r
			return _in_range(c, lo, hi, li, ri)

		# fallback
		return current == expected

	def is_dummy_match(self, dummy, ctx_state: Any) -> Tuple[bool, Dict[int, str]]:
		captured: Dict[int, str] = {}
		for ins in (dummy.inspections or []):
			val = self._read_current_value(ctx_state, ins)
			captured[ins.id] = val
			if not self._inspection_match(val, ins):
				return False, captured
		return True, captured

	def analyse_test_result(
			self,
			ctx_state: Any,
			*,
			is_predetermined: bool = False,
			predetermined_dummy_id: Optional[int] = None,
	) -> None:
		"""
		- predetermined: check selected dummy (or predetermined_dummy_id). If match -> OK. Else -> NOK.
		- non-predetermined: scan pending dummies; if match -> OK; if none -> do nothing.
		"""
		if not self.dummies():
			return

		# ensure we have a running session and entries
		if self.started_at is None:
			self.start_execution()
		else:
			self.ensure_dummy_result_entries()

		pending = self.remaining_dummies()
		if not pending:
			#self.finish_execution()
			return

		executed_dummy = None
		captured: Dict[int, str] = {}

		if is_predetermined:
			did = predetermined_dummy_id or self.selected_dummy_id
			if did is None:
				return

			dummy = next((d for d in self.dummies() if d.id == did), None)
			if dummy is None:
				return

			ok, cap = self.is_dummy_match(dummy, ctx_state)
			captured = cap

			# RULE: predetermined -> mark OK or NOK on that selected dummy
			self.set_dummy_state(dummy.id, True if ok else False, inspection_values=captured)

			# after marking, move to next pending if OK; if NOK you can also move on (your call)
			#if ok:
			#	self.selected_dummy_id = self._next_pending_dummy_id_after(dummy.id)
			self.persist()
			return

		# non-predetermined: scan pending; if none matches -> do nothing
		for d in pending:
			ok, cap = self.is_dummy_match(d, ctx_state)
			if ok:
				executed_dummy = d
				captured = cap
				break

		if executed_dummy is not None:
			self.set_dummy_state(executed_dummy.id, True, inspection_values=captured)
			self.selected_dummy_id = self._next_pending_dummy_id_after(executed_dummy.id)
			self.persist()
			return

		# RULE: non-predetermined and no match -> do nothing
		return
