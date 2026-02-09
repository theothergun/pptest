from __future__ import annotations

import time
import threading
import queue
from enum import StrEnum

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_registry import SendCmdFn


class Topics(StrEnum):
    TICK = "demo.tick"


class Commands(StrEnum):
    START = "start"
    STOP = "stop"
    RESET = "reset"


def demo_publisher_worker(
        bridge: UiBridge,
        worker_bus: WorkerBus,
        commands: "queue.Queue[tuple[str, dict]]",
        stop: threading.Event,
        send_cmd: SendCmdFn,
) -> None:
    """
	Publishes bus events periodically.
	This worker demonstrates: worker -> WorkerBus.publish(...)
	"""

    running = False
    counter = 0

    def _publish_state() -> None:
        # Optional: publish a state snapshot too (not required for the demo)
        bridge.emit_patch("demo_publisher_state", {"running": running, "counter": counter})

    bridge.emit_notify("DemoPublisher started", type="info")
    _publish_state()

    last_tick = time.time()

    while not stop.is_set() and not bridge.stopped():
        # ---- handle commands ----
        cmd, payload = _get_next_cmd(commands)
        if cmd:
            if cmd == Commands.START:
                running = True
                bridge.emit_notify("Publisher running", type="positive")
                _publish_state()

            elif cmd == Commands.STOP:
                running = False
                bridge.emit_notify("Publisher stopped", type="warning")
                _publish_state()

            elif cmd == Commands.RESET:
                counter = 0
                bridge.emit_notify("Publisher reset", type="info")
                _publish_state()

        # ---- publish tick ----
        now = time.time()
        if running and (now - last_tick) >= 0.2:
            last_tick = now
            counter += 1

            # Publish to bus: subscriber worker will receive this
            worker_bus.publish(Topics.TICK, counter=counter, ts=now)

            # Also push state to UI (so you can see publisher state immediately)
            _publish_state()

        time.sleep(0.02)

    bridge.emit_notify("DemoPublisher stopped", type="warning")


def _get_next_cmd(commands: "queue.Queue[tuple[str, dict]]") -> tuple[str | None, dict]:
    try:
        cmd, payload = commands.get_nowait()
        return cmd, (payload or {})
    except Exception:
        return None, {}
