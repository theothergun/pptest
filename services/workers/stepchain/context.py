from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from loguru import logger

from services.worker_topics import WorkerTopics
from services.worker_commands import TcpClientCommands
from services.worker_names import WorkerName


class StepChainContext:

	def __init__(
		self,
		chain_id: str,
		worker_bus,
		bridge,
		state,
	):
		self.chain_id = chain_id
		self.worker_bus = worker_bus
		self.bridge = bridge
		self.state = state

		# step control
		self.step = 0
		self.step_desc = "-"
		self.next_step: Optional[int] = None
		self.step_entry_time = time.time()
		self.cycle_count = 0
		self.cycle_time = 0.1

		# runtime
		self.data: Dict[str, Any] = {}
		self.error_flag = False
		self.error_message = ""
		self.paused = False

	# ------------------------------------------------------------------ helpers for scripts

	def create_id(self) -> str:
		return uuid.uuid4().hex

	def goto(self, next_step: int) -> None:
		self.next_step = next_step

	def reset(self) -> None:
		self.goto(0)
		self.error_flag = False
		self.error_message = ""

	def step_time(self) -> float:
		return time.time() - self.step_entry_time

	def timeout(self, seconds: float) -> bool:
		return self.step_time() >= seconds

	def cycle(self) -> None:
		self.cycle_count += 1
		if self.next_step is not None:
			if self.next_step != self.step:
				self.step = self.next_step
				self.step_entry_time = time.time()
			self.next_step = None

	# ------------------------------------------------------------------ worker interaction (NEW STANDARD)

	def tcp_send(self, client_id: str, data: Any) -> None:
		self.bridge.send_cmd(
			WorkerName.TCP,
			TcpClientCommands.SEND,
			client_id=client_id,
			data=data,
		)

	# ------------------------------------------------------------------ VALUE API (the important part)

	def wait_for_value(self, source: str, key: str) -> Optional[Any]:
		"""
		Read latest VALUE_CHANGED for a worker/key.
		ScriptWorker writes bus messages into ctx.data["bus"].
		"""
		return (
			self.data
			.get("bus", {})
			.get(source, {})
			.get(key)
		)

	# ------------------------------------------------------------------ state export

	def get_state_dict(self) -> Dict[str, Any]:
		return {
			"chain_id": self.chain_id,
			"step": self.step,
			"step_time": self.step_time(),
			"cycle_count": self.cycle_count,
			"error_flag": self.error_flag,
			"error_message": self.error_message,
			"paused": self.paused,
			"data": dict(self.data),
		}
