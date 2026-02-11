from __future__ import annotations

import fnmatch
import queue
import threading
from dataclasses import dataclass
from typing import Any, DefaultDict, Optional, Union, List, Tuple
from collections import defaultdict
from loguru import logger
from services.worker_topics import WorkerTopics


Topic = Union[WorkerTopics, str]


@dataclass(frozen=True)
class BusMessage:
	topic: str
	payload: dict[str, Any]
	source: str
	source_id: str


class Subscription:
	"""Handle returned by WorkerBus.subscribe(); call close() to unsubscribe."""

	def __init__(self, bus: "WorkerBus", topic: Topic, q: "queue.Queue[BusMessage]", is_pattern: bool) -> None:
		self._bus = bus
		self.topic = topic
		self.queue = q
		self._is_pattern = is_pattern
		self._closed = False

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		self._bus._unsubscribe(self.topic, self.queue, self._is_pattern)


class MultiSubscription:
	"""Handle for multiple topic subscriptions sharing one queue."""

	def __init__(self, subs: List[Subscription]) -> None:
		if not subs:
			raise ValueError("MultiSubscription requires at least one Subscription")

		self._subs = subs
		self.queue = subs[0].queue
		self._closed = False

	@property
	def topics(self) -> List[Topic]:
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

		# Exact topic subscriptions: { "topic.name": [queues...] }
		self._subs_exact: DefaultDict[str, List["queue.Queue[BusMessage]"]] = defaultdict(list)

		# Pattern subscriptions: [("chain*", queue), ("*", queue), ...]
		self._subs_pattern: List[Tuple[str, "queue.Queue[BusMessage]"]] = []

	# ------------------------------------------------------------------ internals

	def _topic_to_str(self, topic: Topic) -> str:
		# WorkerTopics might be Enum/StrEnum or similar; str() is safest.
		# If WorkerTopics is StrEnum, str(topic) returns 'WorkerTopics.X' sometimes;
		# topic.value is usually the string. We try value first if present.
		if hasattr(topic, "value"):
			try:
				return str(topic.value)
			except Exception:
				pass
		return str(topic)

	def _is_pattern_topic(self, topic_str: str) -> bool:
		# Treat glob metacharacters as pattern subscription.
		return any(ch in topic_str for ch in ("*", "?", "["))

	# ------------------------------------------------------------------ subscribe

	def subscribe(
		self,
		topic: Topic,
		q: Optional["queue.Queue[BusMessage]"] = None,
	) -> Subscription:
		if q is None:
			q = queue.Queue()

		topic_str = self._topic_to_str(topic)
		is_pattern = self._is_pattern_topic(topic_str)

		with self._lock:
			if is_pattern:
				self._subs_pattern.append((topic_str, q))
			else:
				self._subs_exact[topic_str].append(q)

		return Subscription(self, topic, q, is_pattern=is_pattern)

	def subscribe_many(
		self,
		topics: List[Topic],
		q: Optional["queue.Queue[BusMessage]"] = None,
	) -> MultiSubscription:
		if not topics:
			raise ValueError("topics must not be empty")
		if q is None:
			q = queue.Queue()
		subs = [self.subscribe(topic, q) for topic in topics]
		return MultiSubscription(subs)

	def _unsubscribe(self, topic: Topic, q: "queue.Queue[BusMessage]", is_pattern: bool) -> None:
		topic_str = self._topic_to_str(topic)

		with self._lock:
			if is_pattern:
				# Remove one matching tuple (topic_str, q)
				for i in range(len(self._subs_pattern) - 1, -1, -1):
					pat, pq = self._subs_pattern[i]
					if pat == topic_str and pq is q:
						self._subs_pattern.pop(i)
						break
				return

			lst = self._subs_exact.get(topic_str)
			if not lst:
				return
			try:
				lst.remove(q)
			except ValueError:
				return
			if not lst:
				self._subs_exact.pop(topic_str, None)

	# ------------------------------------------------------------------ publish

	def publish(
		self,
		topic: Topic,
		source: str,
		source_id: str,
		**payload: Any,
	) -> None:
		topic_str = self._topic_to_str(topic)
		msg = BusMessage(topic_str, payload, source, source_id)

		with self._lock:
			# Exact targets
			targets = list(self._subs_exact.get(topic_str, ()))

			# Pattern targets
			patterns = list(self._subs_pattern)

		for pat, q in patterns:
			# fnmatch is case-sensitive with fnmatchcase
			if fnmatch.fnmatchcase(topic_str, pat):
				targets.append(q)
		logger.trace(f"[publish] Bus-Message published {msg}")
		for q in targets:
			q.put(msg)
