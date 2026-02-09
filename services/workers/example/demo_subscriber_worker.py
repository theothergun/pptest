from __future__ import annotations

import time
import threading
import queue
from enum import StrEnum

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus, BusMessage
from services.worker_registry import SendCmdFn
from services.workers.example.demo_publisher_worker import Topics as PubTopics


class Commands(StrEnum):
	CLEAR = "clear"


def demo_subscriber_worker(
	bridge: UiBridge,
	worker_bus: WorkerBus,
	commands: "queue.Queue[tuple[str, dict]]",
	stop: threading.Event,
	send_cmd: SendCmdFn,
) -> None:
	"""
	Subscribes to WorkerBus and pushes state changes to UI via UiBridge.
	Demonstrates: worker -> WorkerBus.subscribe(...) -> consume queue -> UiBridge.emit_patch(...)
	"""

	sub = worker_bus.subscribe(PubTopics.TICK)

	received_count = 0
	last_counter = None
	last_ts = None

	def _push_state() -> None:
		bridge.emit_patch(
			"demo_subscriber_state",
			{
				"received_count": received_count,
				"last_counter": last_counter,
				"last_ts": last_ts,
			},
		)

	bridge.emit_notify("DemoSubscriber started (listening on %s)" % str(PubTopics.TICK), type="info")
	_push_state()

	while not stop.is_set() and not bridge.stopped():
		# ---- handle commands ----
		cmd, payload = _get_next_cmd(commands)
		if cmd:
			if cmd == Commands.CLEAR:
				received_count = 0
				last_counter = None
				last_ts = None
				bridge.emit_notify("Subscriber cleared", type="info")
				_push_state()

		# ---- consume bus messages ----
		msg = _get_next_bus_msg(sub.queue)
		if msg is not None:
			received_count += 1
			last_counter = msg.payload.get("counter")
			last_ts = msg.payload.get("ts")
			_push_state()

		time.sleep(0.01)

	# cleanup subscription
	try:
		sub.close()
	except Exception:
		pass

	bridge.emit_notify("DemoSubscriber stopped", type="warning")


def _get_next_cmd(commands: "queue.Queue[tuple[str, dict]]") -> tuple[str | None, dict]:
	try:
		cmd, payload = commands.get_nowait()
		return cmd, (payload or {})
	except Exception:
		return None, {}


def _get_next_bus_msg(q: "queue.Queue[BusMessage]") -> BusMessage | None:
	try:
		return q.get_nowait()
	except Exception:
		return None
