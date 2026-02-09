from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, DefaultDict
from collections import defaultdict

from services.worker_topics import WorkerTopics


@dataclass(frozen=True)
class BusMessage:
	topic: WorkerTopics
	payload: dict[str, Any]
	source: str
	source_id: str


class Subscription:
	"""Handle returned by WorkerBus.subscribe(); call close() to unsubscribe."""

	def __init__(self, bus: "WorkerBus", topic: WorkerTopics, q: "queue.Queue[BusMessage]") -> None:
		self._bus = bus
		self.topic = topic
		self.queue = q
		self._closed = False

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		self._bus._unsubscribe(self.topic, self.queue)


class MultiSubscription:
	"""Handle for multiple topic subscriptions sharing one queue."""

	def __init__(self, subs: list[Subscription]) -> None:
		if not subs:
			raise ValueError("MultiSubscription requires at least one Subscription")

		self._subs = subs
		self.queue = subs[0].queue
		self._closed = False

	@property
	def topics(self) -> list[WorkerTopics]:
		return [s.topic for s in self._subs]

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		for s in self._subs:
			s.close()


class WorkerBus:
	"""In-process pub/sub for worker↔worker messages (per client session)."""

	def __init__(self) -> None:
		self._lock = threading.Lock()
		self._subs: DefaultDict[WorkerTopics, list["queue.Queue[BusMessage]"]] = defaultdict(list)

	def subscribe(
		self,
		topic: WorkerTopics,
		q: "queue.Queue[BusMessage] | None" = None,
	) -> Subscription:
		if q is None:
			q = queue.Queue()

		with self._lock:
			self._subs[topic].append(q)

		return Subscription(self, topic, q)

	def _unsubscribe(self, topic: WorkerTopics, q: "queue.Queue[BusMessage]") -> None:
		with self._lock:
			lst = self._subs.get(topic)
			if not lst:
				return
			try:
				lst.remove(q)
			except ValueError:
				return
			if not lst:
				self._subs.pop(topic, None)

	def subscribe_many(
		self,
		topics: list[WorkerTopics],
		q: "queue.Queue[BusMessage] | None" = None,
	) -> MultiSubscription:
		if not topics:
			raise ValueError("topics must not be empty")
		if q is None:
			q = queue.Queue()
		subs = [self.subscribe(topic, q) for topic in topics]
		return MultiSubscription(subs)

	def publish(
		self,
		topic: WorkerTopics,
		source: str,
		source_id: str,
		**payload: Any,
	) -> None:
		msg = BusMessage(topic, payload, source, source_id)

		with self._lock:
			targets = list(self._subs.get(topic, ()))

		for q in targets:
			q.put(msg)
