from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, Optional

from loguru import logger

from services.workers.stepchain.apis.values_api import ValuesApi
from services.workers.stepchain.apis.vars_api import VarsApi
from services.workers.stepchain.apis.ui_api import UiApi
from services.workers.stepchain.apis.flow_api import FlowApi
from services.workers.stepchain.apis.timing_api import TimingApi


class StepChainContext:
	"""
	Internal engine context for one running step chain instance.

	IMPORTANT:
	- This object is owned by the runtime.
	- User scripts MUST NOT receive this object directly.
	- Scripts should receive `public`, which exposes a stable, limited API.
	"""

	def __init__(
		self,
		chain_id: str,
		worker_bus: Any,
		bridge: Any,
		state: Any,
	) -> None:
		self.chain_id = str(chain_id or uuid.uuid4())
		self.worker_bus = worker_bus
		self.bridge = bridge
		self.state = state

		# Runtime input snapshots (bus values)
		self.data: Dict[str, Dict[str, Any]] = {}

		# Engine state (managed by runtime)
		self.step = 0
		self.next_step = 0
		self.step_time = 0.0
		self.cycle_time = 0.1
		self.cycle_count = 0
		self.paused = False

		# Status / error reporting
		self.error_flag = False
		self.error_message = ""
		self.step_desc = ""

		# Script-owned variables (persist across ticks)
		self._vars: Dict[str, Any] = {}

		# Script-owned UI state (persist across ticks; diffed before publishing)
		self._ui_state: Optional[Dict[str, Any]] = None

		# Computed helpers for "last" lookup
		self._last_seen_by_source: Dict[str, str] = {}

		# Cached public API wrapper
		self._public: Optional[PublicStepChainContext] = None

		logger.bind(component="StepChainContext", chain_id=self.chain_id).debug("created")

	@property
	def public(self) -> "PublicStepChainContext":
		"""Public, script-safe API wrapper."""
		if self._public is None:
			self._public = PublicStepChainContext(self)
		return self._public

	def _update_bus_value(self, source: str, source_id: str, payload: Any) -> None:
		"""Runtime hook: called by ScriptWorker when a VALUE_CHANGED event arrives."""
		source = str(source or "unknown")
		source_id = str(source_id or "")

		if source not in self.data:
			self.data[source] = {}

		self.data[source][source_id] = payload
		self._last_seen_by_source[source] = source_id

	def get_state(self) -> Dict[str, Any]:
		"""State exported to UI; includes runtime state, vars, and ui_state."""
		ui_state = self._ui_state if isinstance(self._ui_state, dict) else {}

		return {
			"chain_id": self.chain_id,
			"step": self.step,
			"step_time": self.step_time,
			"cycle_count": self.cycle_count,
			"error_flag": self.error_flag,
			"error_message": self.error_message,
			"step_desc": self.public.step_desc,
			"paused": self.paused,
			"data": copy.deepcopy(self._vars),
			"ui_state": copy.deepcopy(ui_state),
		}


class PublicStepChainContext:
	"""Stable, script-facing context (public API)."""

	def __init__(self, ctx: StepChainContext) -> None:
		self._ctx = ctx

		self.values = ValuesApi(ctx)
		self.vars = VarsApi(ctx)
		self.ui = UiApi(ctx)
		self.flow = FlowApi(ctx)
		self.timing = TimingApi(ctx)

	@property
	def chain_id(self) -> str:
		return self._ctx.chain_id

	@property
	def cycle_count(self) -> int:
		return int(self._ctx.cycle_count)

	@property
	def paused(self) -> bool:
		return bool(self._ctx.paused)

	@property
	def error_flag(self) -> bool:
		return bool(self._ctx.error_flag)

	@property
	def error_message(self) -> str:
		return str(self._ctx.error_message or "")

	@property
	def step(self) -> int:
		return int(self._ctx.step)

	@property
	def step_desc(self) -> str:
		return str(self._ctx.step_desc or "")

	def goto(self, step: int, desc: str = "") -> None:
		self.flow.goto(step=step, desc=desc)

	def fail(self, message: str) -> None:
		self.flow.fail(message)

	def clear_error(self) -> None:
		self.flow.clear_error()

	def log(self, message: str) -> None:
		self.ui.log(message)

	def set_cycle_time(self, seconds: float) -> None:
		self.timing.set_cycle_time(seconds)

	def set_step_desc(self, value: str) -> None:
		self._ctx.step_desc = value

	def snapshot(self) -> Dict[str, Any]:
		ui_state = self._ctx._ui_state if isinstance(self._ctx._ui_state, dict) else {}
		return {
			"chain_id": self._ctx.chain_id,
			"step": self._ctx.step,
			"cycle_count": self._ctx.cycle_count,
			"error_flag": self._ctx.error_flag,
			"error_message": self._ctx.error_message,
			"step_desc": self.step_desc,
			"paused": self._ctx.paused,
			"vars": self.vars.as_dict(),
			"ui_state": dict(ui_state),
		}
