# services/workers/base_worker.py
from __future__ import annotations

import queue
import threading
from contextlib import contextmanager
from typing import Any, Callable, Optional

from loguru import logger

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_registry import SendCmdFn
from services.worker_topics import WorkerTopics


CommandPayload = dict[str, Any]
CommandHandler = Callable[[CommandPayload], None]


class BaseWorker:
	def __init__(
		self,
		*,
		name: str,
		bridge: UiBridge,
		worker_bus: WorkerBus,
		commands: "queue.Queue[tuple[str, dict]]",
		stop: threading.Event,
		send_cmd: SendCmdFn,
	) -> None:
		self.name = name
		self.bridge = bridge
		self.worker_bus = worker_bus
		self.commands = commands
		self.stop_event = stop
		self.send_cmd = send_cmd
		self.log = logger.bind(component=name)

		self._running = False
		self._connected = False

		# IMPORTANT: must be set by workers before publishing
		self.current_source_id: str = ""

		# Optional: track subscriptions to close on shutdown
		self._subs: list[Any] = []

	# ------------------------------------------------------------------ lifecycle

	def should_stop(self) -> bool:
		return self.stop_event.is_set() or self.bridge.stopped()

	def start(self) -> None:
		self._running = True
		self.log.info("worker started")

	def stop(self) -> None:
		self.stop_event.set()
		try:
			self.commands.put_nowait(("__stop__", {}))
		except queue.Full:
			pass
		self._running = False
		self.log.info("worker stop requested")

	def mark_stopped(self) -> None:
		self._running = False
		self.log.info("worker stopped")

	def set_connected(self, connected: bool) -> None:
		if self._connected == connected:
			return
		self._connected = connected
		self.log.info(f"connection status changed: connected={connected}")

	def is_connected(self) -> bool:
		return self._connected

	def is_running(self) -> bool:
		return self._running

	# ------------------------------------------------------------------ subscriptions

	def add_subscription(self, sub: Any) -> Any:
		"""
		Register a subscription-like object that has a .close() method.
		Workers can call this for WorkerBus subscriptions to ensure clean shutdown.
		"""
		self._subs.append(sub)
		return sub

	def close_subscriptions(self) -> None:
		for sub in list(self._subs):
			try:
				if hasattr(sub, "close") and callable(getattr(sub, "close")):
					sub.close()
			except Exception as ex:
				self.log.debug(f"failed closing subscription: {ex!r}")
		self._subs = []

	# ------------------------------------------------------------------ UI bridge

	def notify(self, message: str, type_: str = "info") -> None:
		self.bridge.emit_notify(message, type_)

	def emit_patch(self, key: str, value: Any) -> None:
		self.bridge.emit_patch(key, value)

	def emit_error(self, **payload: Any) -> None:
		self.bridge.emit_error(**payload)

	def emit_error_resolved(self, error_id: str) -> None:
		self.bridge.emit_error_resolved(error_id=error_id)

	# ------------------------------------------------------------------ BUS (STRICT CONTRACT)

	def _pub(self, topic: WorkerTopics, **payload: Any) -> None:
		if not self.current_source_id:
			self.log.error(f"publish without source_id! topic={topic} payload={payload}")
			return

		self.worker_bus.publish(
			topic=topic,
			source=self.name,
			source_id=self.current_source_id,
			**payload
		)

	def publish_connected(self) -> None:
		self._pub(WorkerTopics.CLIENT_CONNECTED)

	def publish_disconnected(self, reason: str) -> None:
		self._pub(WorkerTopics.CLIENT_DISCONNECTED, reason=reason)

	def publish_value(self, key: str, value: Any) -> None:
		"""
		UI pages (like Scripts Lab) subscribe to WorkerTopics.VALUE_CHANGED.
		So publishing values must use VALUE_CHANGED, not a custom topic.
		"""
		self._pub(WorkerTopics.VALUE_CHANGED, key=key, value=value)

	def publish_write_finished(self, key: str) -> None:
		self._pub(WorkerTopics.WRITE_FINISHED, key=key)

	def publish_write_error(self, key: Optional[str], error: str) -> None:
		self._pub(WorkerTopics.WRITE_ERROR, key=key, error=error, action="write")

	def publish_error(self, key: Optional[str], action: str, error: str) -> None:
		self._pub(WorkerTopics.ERROR, key=key, action=action, error=error)

	# ------------------------------------------------------------------ publish helpers

	@contextmanager
	def as_source(self, source_id: str):
		"""
		Temporarily set current_source_id for publish calls.
		"""
		prev = self.current_source_id
		self.current_source_id = str(source_id or "")
		try:
			yield
		finally:
			self.current_source_id = prev

	def publish_value_as(self, source_id: str, key: str, value: Any) -> None:
		with self.as_source(source_id):
			self.publish_value(key=key, value=value)

	def publish_error_as(self, source_id: str, key: Optional[str], action: str, error: str) -> None:
		with self.as_source(source_id):
			self.publish_error(key=key, action=action, error=error)

	def publish_connected_as(self, source_id: str) -> None:
		with self.as_source(source_id):
			self.publish_connected()

	def publish_disconnected_as(self, source_id: str, reason: str) -> None:
		with self.as_source(source_id):
			self.publish_disconnected(reason)

	def publish_write_finished_as(self, source_id: str, key: str) -> None:
		with self.as_source(source_id):
			self.publish_write_finished(key)

	def publish_write_error_as(self, source_id: str, key: Optional[str], error: str) -> None:
		with self.as_source(source_id):
			self.publish_write_error(key, error)

	# ------------------------------------------------------------------ command helpers

	def pop_command(self, timeout: float = 0.1) -> tuple[Optional[str], dict]:
		try:
			cmd, payload = self.commands.get(timeout=timeout)
		except queue.Empty:
			return None, {}
		return cmd, payload

	def drain_commands(self, limit: int = 50) -> list[tuple[str, dict]]:
		items: list[tuple[str, dict]] = []
		for _ in range(limit):
			try:
				items.append(self.commands.get_nowait())
			except queue.Empty:
				break
		return items

	def dispatch_commands(
		self,
		handlers: dict[str, CommandHandler],
		*,
		limit: int = 50,
		unknown_handler: Optional[CommandHandler] = None,
	) -> None:
		for cmd, payload in self.drain_commands(limit=limit):
			name = str(cmd or "")
			data = payload or {}

			if name == "__stop__":
				return

			handler = handlers.get(name)
			if handler is None:
				if unknown_handler is not None:
					try:
						unknown_handler(data)
					except Exception as ex:
						self.publish_error_as(self.name, key=self.name, action="cmd_unknown_handler", error=str(ex))
				continue

			try:
				handler(data)
			except Exception as ex:
				self.publish_error_as(self.name, key=self.name, action=f"cmd:{name}", error=str(ex))
				self.log.exception(f"command handler crashed: cmd={name} payload={data!r}")
