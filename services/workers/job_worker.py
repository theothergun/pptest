from __future__ import annotations

import time
import threading
import queue

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus, Subscription
from services.worker_registry import SendCmdFn
from services.worker_names import WorkerName

from services.worker_commands import DeviceWorkerCommands as DeviceCmd
from services.worker_commands import JobWorkerCommands as Commands
from services.worker_topics import DeviceWorkerTopics as DeviceTopics
from services.worker_topics import JobWorkerTopics as Topics

#Another test worker
def job_worker(
    bridge: UiBridge,
    worker_bus: WorkerBus,
    commands: "queue.Queue[tuple[str, dict]]",
    stop: threading.Event,
    send_cmd: SendCmdFn
) -> None:
    bridge.emit_notify("Job worker started", "info")

    sub = worker_bus.subscribe(DeviceTopics.SCAN_RESULT)
    # or list of subscription
    #subs =
    try:
        while not stop.is_set() and not bridge.stopped():
            _execute_cmd_if_found(bridge, worker_bus, commands, stop, send_cmd)

    finally:
            sub.close()

def _execute_cmd_if_found(bridge:UiBridge, worker_bus: WorkerBus,
        commands:"queue.Queue[tuple[str, dict]]", stop: threading.Event, send_cmd: SendCmdFn) -> bool:
    """Return str True if stop command was found, False otherwise"""
    payload = None
    try:
        cmd, payload = commands.get(timeout=0.2)
    except queue.Empty:
        cmd = None

    # control plane
    if cmd == "__stop__":  # internal stop mechanism use to wake the command queue if blocked on get()
        return True

    # domain plane
    if cmd == Commands.STOP:
        # do what you have to do
        # if this means stop the thread then just
        stop.set()
        return True

    elif cmd == Commands.RUN_JOB:
        name = payload.get("name", "job")
        bridge.emit_patch("job_status", f"Running {name}...")
        send_cmd(WorkerName.DEVICE, DeviceCmd.TRIGGER, {})
        time.sleep(1.0)
        bridge.emit_patch("job_status", f"Done: {name}")
        bridge.emit_notify(f"Job {name} finished", "positive")

    return False


def _check_message_publication(subscription: Subscription):
    try:
        msg = subscription.queue.get_nowait()
        if msg.topic == DeviceTopics.SCAN_RESULT:
            # do something with result inside the payload
            pass
    except queue.Empty:
        msg = None
