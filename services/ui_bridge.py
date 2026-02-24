from __future__ import annotations

import queue
import threading
from collections import defaultdict
from dataclasses import dataclass, is_dataclass, asdict
from enum import StrEnum
from typing import Any, Callable, DefaultDict, Union

from nicegui import ui
from loguru import logger

Topic = Union[str, StrEnum]


# ---------- events delivered to UI-side subscribers ----------
@dataclass(frozen=True)
class UiBusMessage:
    topic: str
    payload: dict[str, Any]


# ---------- worker -> UI messages (bridge inbox) ----------
@dataclass(frozen=True)
class Patch:
    """Update one attribute on ctx.state: setattr(state, key, value)."""
    key: str
    value: Any


@dataclass(frozen=True)
class ReplaceState:
    """Update multiple attributes on ctx.state (useful for initial sync/resync)."""
    values: dict[str, Any]


@dataclass(frozen=True)
class Notify:
    """Show a NiceGUI notification."""
    message: str
    type: str = "info"  # "positive" | "negative" | "warning" | "info"


@dataclass(frozen=True)
class Call:
    """Call a function on the UI thread."""
    fn: Callable[[], None]


@dataclass(frozen=True)
class ErrorEvent:
    error_id: str
    source: str
    message: str
    details: str = ""

@dataclass(frozen=True)
class RequestUiState:
    """Worker requests the UI thread to publish a full ui.state snapshot."""
    pass

@dataclass(frozen=True)
class ErrorResolvedEvent:
    """Worker reports that an active error is resolved and should be removed."""
    error_id: str


UiMsg = Patch | ReplaceState | Notify | Call | ErrorEvent | ErrorResolvedEvent | RequestUiState


# ---------- subscriptions ----------
class Subscription:
    """Handle returned by UiBridge.subscribe(); call close() to unsubscribe."""

    def __init__(self, bridge: "UiBridge", topic: str, q: "queue.Queue[UiBusMessage]") -> None:
        self._bridge = bridge
        self.topic = topic
        self.queue = q
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bridge._unsubscribe(self.topic, self.queue)


class MultiSubscription:
    """Handle for multiple topic subscriptions sharing one queue."""

    def __init__(self, subs: list[Subscription]) -> None:
        if not subs:
            raise ValueError("MultiSubscription requires at least one Subscription")
        self._subs = subs
        self.queue = subs[0].queue  # shared queue
        self._closed = False

    @property
    def topics(self) -> list[str]:
        return [s.topic for s in self._subs]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for s in self._subs:
            s.close()


# ---------- bridge ----------
class UiBridge:
    """
    Thread-safe bridge between background worker threads and the NiceGUI UI thread.

    Worker API (thread-safe):
      - emit_patch(key, value)
      - emit_replace_state({...})
      - emit_notify(...)
      - emit_call(...)
      - emit_error(...)
      - emit_error_resolved(...)

    UI API (UI-thread):
      - flush(ctx)             # apply messages to ctx.state and publish events
      - subscribe(topic)       # exact or prefix wildcard: "state.*"
      - subscribe_many([...])  # multiple topics, shared queue

    Important pattern:
      - Workers DO NOT touch ctx.state directly.
      - flush() updates ctx.state (dumb dataclass) and THEN publishes UiBusMessage
        events to subscribers so "interested parties" can react.
    """

    def __init__(self) -> None:
        self._outbox: "queue.Queue[UiMsg]" = queue.Queue()
        self._dirty = threading.Event()
        self._stop = threading.Event()

        self._sub_lock = threading.Lock()
        self._subs: DefaultDict[str, list["queue.Queue[UiBusMessage]"]] = defaultdict(list)
        self._prefix_subs: DefaultDict[str, list["queue.Queue[UiBusMessage]"]] = defaultdict(list)

    # ----- worker -> UI (thread-safe enqueue) -----
    def emit_patch(self, key: str, value: Any) -> None:
        self._outbox.put(Patch(key, value))
        self._dirty.set()

    def emit_replace_state(self, values: dict[str, Any]) -> None:
        self._outbox.put(ReplaceState(values))
        self._dirty.set()

    def emit_notify(self, message: str, type: str = "info") -> None:
        self._outbox.put(Notify(message, type))
        self._dirty.set()

    def emit_call(self, fn: Callable[[], None]) -> None:
        self._outbox.put(Call(fn))
        self._dirty.set()

    def emit_error(self, *, error_id: str, source: str, message: str, details: str = "") -> None:
        self._outbox.put(ErrorEvent(error_id, source, message, details))
        self._dirty.set()

    def emit_error_resolved(self, *, error_id: str) -> None:
        self._outbox.put(ErrorResolvedEvent(error_id=error_id))
        self._dirty.set()

    def request_ui_state(self) -> None:
        """Worker thread: ask UI thread to publish full ui.state snapshot."""
        self._outbox.put(RequestUiState())
        self._dirty.set()

    # ----- lifecycle -----
    def stop(self) -> None:
        self._stop.set()
        self._dirty.set()

    def stopped(self) -> bool:
        return self._stop.is_set()

    # ----- UI-side subscribe API -----
    def subscribe(
        self,
        topic: Topic,
        q: "queue.Queue[UiBusMessage] | None" = None,
    ) -> Subscription:
        topic_str = str(topic)
        if q is None:
            q = queue.Queue()

        with self._sub_lock:
            if topic_str.endswith("*"):
                prefix = topic_str[:-1]
                self._prefix_subs[prefix].append(q)
            else:
                self._subs[topic_str].append(q)

        return Subscription(self, topic_str, q)

    def subscribe_many(
        self,
        topics: list[Topic],
        q: "queue.Queue[UiBusMessage] | None" = None,
    ) -> MultiSubscription:
        if not topics:
            raise ValueError("topics must not be empty")

        if q is None:
            q = queue.Queue()

        subs = [self.subscribe(t, q) for t in topics]
        return MultiSubscription(subs)

    def _unsubscribe(self, topic: str, q: "queue.Queue[UiBusMessage]") -> None:
        with self._sub_lock:
            if topic.endswith("*"):
                prefix = topic[:-1]
                lst = self._prefix_subs.get(prefix)
                if not lst:
                    return
                try:
                    lst.remove(q)
                except ValueError:
                    return
                if not lst:
                    self._prefix_subs.pop(prefix, None)
                return

            lst = self._subs.get(topic)
            if not lst:
                return
            try:
                lst.remove(q)
            except ValueError:
                return
            if not lst:
                self._subs.pop(topic, None)

    # ----- UI thread flush -----
    def flush(self, ctx: Any, *, max_items: int = 200) -> None:
        """
        UI thread: apply queued messages.
        - cheap when idle (uses dirty flag)
        - applies up to max_items per tick
        - ALWAYS: update ctx.state first, THEN publish UiBusMessage to subscribers
        """
        if not self._dirty.is_set():
            return

        self._dirty.clear()

        processed = 0
        while processed < max_items:
            try:
                msg = self._outbox.get_nowait()
            except queue.Empty:
                break

            if isinstance(msg, Patch):
                self._apply_patch(ctx, msg.key, msg.value)

            elif isinstance(msg, ReplaceState):
                self._apply_replace_state(ctx, msg.values)

            elif isinstance(msg, Notify):
                ui.notify(msg.message, type=msg.type)
                # optional event for listeners
                self._deliver_to_subscribers(UiBusMessage("ui.notify", {"message": msg.message, "type": msg.type}))

            elif isinstance(msg, Call):
                try:
                    msg.fn()
                except Exception as e:
                    ui.notify(f"UI call failed: {e}", type="negative")
                    self._deliver_to_subscribers(UiBusMessage("ui.call_error", {"error": str(e)}))

            elif isinstance(msg, ErrorEvent):
                # Local import to avoid import-time cycles
                from layout.errors_state import upsert_error

                upsert_error(ctx, msg.error_id, source=msg.source, message=msg.message, details=msg.details)
                self._deliver_to_subscribers(UiBusMessage("errors.upsert", {
                    "error_id": msg.error_id,
                    "source": msg.source,
                    "message": msg.message,
                    "details": msg.details,
                }))
                # Keep ctx.state summary in sync
                self._sync_error_count(ctx)

            elif isinstance(msg, ErrorResolvedEvent):
                from layout.errors_state import resolve_error

                resolve_error(ctx, msg.error_id)
                self._deliver_to_subscribers(UiBusMessage("errors.resolved", {"error_id": msg.error_id}))
                self._sync_error_count(ctx)

            elif isinstance(msg, RequestUiState):
                state = getattr(ctx, "state", None)
                if state is None:
                    continue
                #full snapshot (dataclass-friendly)
                payload = asdict(state)
                self._deliver_to_subscribers(UiBusMessage("state", payload))

            processed += 1

        if not self._outbox.empty():
            self._dirty.set()

    def ui_publish_event(self, topic: Topic, **payload: Any) -> None:
        """UI thread: publish an event to UiBridge subscribers immediately.
        Intended for UI->workers (and UI listeners)."""
        self._deliver_to_subscribers(UiBusMessage(str(topic), payload))

    # ----- helpers: apply state then publish events -----
    def _apply_patch(self, ctx: Any, key: str, value: Any) -> None:
        state = getattr(ctx, "state", None)
        if state is None:
            return

        setattr(state, key, value)
        self._deliver_to_subscribers(UiBusMessage(f"state.{key}", {key: value}))

    def _apply_replace_state(self, ctx: Any, values: dict[str, Any]) -> None:
        state = getattr(ctx, "state", None)
        if state is None:
            return

        for k, v in values.items():
            setattr(state, k, v)
        self._deliver_to_subscribers(UiBusMessage("state", dict(values)))

    def _sync_error_count(self, ctx: Any) -> None:
        state = getattr(ctx, "state", None)
        if state is None:
            return
        count = self._get_active_error_count()
        setattr(state, "error_count", count)
        self._deliver_to_subscribers(UiBusMessage("state.error_count", {"error_count": count}))



    def _summarize_payload(self, payload: dict[str, Any], *, max_items: int = 12, max_text: int = 180) -> dict[str, Any]:
        items = list(payload.items())[:max_items]
        summary: dict[str, Any] = {}
        for k, v in items:
            text = str(v)
            summary[str(k)] = f"{text[:max_text]}...({len(text)} chars)" if len(text) > max_text else text
        return summary

    def _deliver_to_subscribers(self, msg: UiBusMessage) -> None:
        with self._sub_lock:
            exact_targets = list(self._subs.get(msg.topic, ()))

            prefix_targets: list["queue.Queue[UiBusMessage]"] = []
            for prefix, queues in self._prefix_subs.items():
                if msg.topic.startswith(prefix):
                    prefix_targets.extend(queues)

        # de-dup queues (same queue can match exact + prefix)
        seen = set()
        targets: list["queue.Queue[UiBusMessage]"] = []
        for q in exact_targets + prefix_targets:
            qid = id(q)
            if qid in seen:
                continue
            seen.add(qid)
            targets.append(q)

        payload_summary = self._summarize_payload(msg.payload)
        logger.trace(f"[_deliver_to_subscribers] - ui_bus_message - topic={msg.topic} targets={len(targets)} payload={payload_summary}")

        for q in targets:
            q.put(msg)

    def _get_active_error_count(self) -> int:
        from nicegui import app
        return len(app.storage.user.get("errors_active", {}))
