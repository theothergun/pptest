# pages/dummy/dummy_scheduler.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from pages.dummy.historization import get_last_finished_at


def _utc_now() -> datetime:
	return datetime.now(timezone.utc)


def _to_seconds(value: int, unit: str) -> int:
	u = (unit or "").strip().lower()
	v = max(int(value or 0), 0)

	if u in ("sec", "secs", "second", "seconds"):
		return v
	if u in ("min", "mins", "minute", "minutes"):
		return v * 60
	if u in ("hour", "hours", "h"):
		return v * 3600
	if u in ("day", "days", "d"):
		return v * 86400
	if u in ("week", "weeks", "w"):
		return v * 7 * 86400

	# fallback: treat unknown unit as seconds
	return v

def _interval_to_timedelta(value: int, unit: str) -> timedelta:
	u = (unit or "").strip().lower()
	if u in ("sec", "secs", "second", "seconds"):
		return timedelta(seconds=value)
	if u in ("min", "mins", "minute", "minutes"):
		return timedelta(minutes=value)
	if u in ("hour", "hours", "h"):
		return timedelta(hours=value)
	if u in ("day", "days", "d"):
		return timedelta(days=value)
	if u in ("week", "weeks", "w"):
		return timedelta(weeks=value)
	# fallback: minutes
	return timedelta(minutes=value)


@dataclass
class DummyScheduler:
	"""
	Machine-wide scheduler engine.

	- Reads configuration from edition_state.scheduler
	- Reads/writes runtime flags via ctx.state + ctx.bridge.emit_patch(...)
	- Does NOT touch UI; controller does UI handling.
	"""

	def __init__(self, *, ctx: Any, edition_state: Any) -> None:
		self.ctx = ctx
		self.edition_state = edition_state

		self._machine_start_fired: bool = False

		# interval anchor (loaded once from history at runtime start)
		self._interval_anchor_loaded: bool = False
		self._last_finished_at: Optional[datetime] = None

	# -------------------------
	# Interval anchor
	# -------------------------
	def _load_interval_anchor_once(self) -> None:
		if self._interval_anchor_loaded:
			return
		self._interval_anchor_loaded = True

		# If later you want per-set anchors, pass set_name=<selected set name>
		self._last_finished_at = get_last_finished_at()

	def notify_execution_finished(self, finished_at: Optional[datetime] = None) -> None:
		"""Call from controller after historization to update next interval anchor."""
		self._last_finished_at = finished_at or _utc_now()


	def _scheduler(self) -> Any:
		return getattr(self.edition_state, "scheduler", None)

	def _enabled(self) -> bool:
		sched = self._scheduler()
		return bool(sched and getattr(sched, "is_dummy_activated", False))


	def notify_program_changed(self) -> None:
		"""
		Call this when your system detects a program change.
		(Alternatively, controller can call this when it receives dummy_* topics.)
		"""
		sched = self._scheduler()
		if not self._enabled():
			return
		if not sched or not getattr(sched, "on_program_change", False):
			return

		self._trigger_start()

	# -------------------------
	# Scheduler loop
	# -------------------------
	def tick(self) -> None:
		"""
		Called periodically. Decides if a dummy run should be started.
		Starting is done by emitting patches to ctx.bridge (machine-wide state).
		"""
		sched = getattr(self.edition_state, "scheduler", None)
		if not sched or not getattr(sched, "is_dummy_activated", False):
			return

		now = _utc_now()

		# Don't start another run while one is running
		if getattr(self.ctx.state, "dummy_test_is_running", False):
			return

		# 1) On machine start (fire once)
		if getattr(sched, "on_machine_start", False) and not self._machine_start_fired:
			self._machine_start_fired = True
			self._trigger_start()
			return  # avoid double-trigger same tick

		# 2) On interval
		if getattr(sched, "on_interval", False):
			self._load_interval_anchor_once()

			# If no history exists yet, run immediately once and anchor from now.
			# If you prefer to wait one full interval before first run,
			# replace this block with: self._last_finished_at = now; return
			if self._last_finished_at is None:
				self._trigger_start()
				self._last_finished_at = now
				return

			value = int(getattr(sched, "interval_value", 1) or 1)
			unit = str(getattr(sched, "interval_unit", "Minutes") or "Minutes")
			delta = _interval_to_timedelta(value, unit)

			next_due = self._last_finished_at + delta
			if now >= next_due:
				self._trigger_start()
				# anchor from "now" (simple). If you want no drift, anchor from next_due instead:
				# self._last_finished_at = next_due
				self._last_finished_at = now
				return

	# 3) On program change etc. (keep your existing logic here if you have it)
	# if getattr(sched, "on_program_change", False) and <your condition>:
	#     self._trigger_start()

	# -------------------------
	# Start run (state patches)
	# -------------------------
	def _trigger_start(self) -> None:
		"""
		Start a dummy run by emitting state patches.
		The controller + execution logic will handle the rest.
		"""
		# show window + mark running
		self.ctx.bridge.emit_patch("dummy_is_enabled", True)