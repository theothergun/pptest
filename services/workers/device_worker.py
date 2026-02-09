from __future__ import annotations

import time
import threading
import queue

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_commands import DeviceWorkerCommands as Commands
from services.worker_registry import SendCmdFn
from services.worker_topics import DeviceWorkerTopics as Topics
from services.workers.base_worker import BaseWorker

#TEst Worker
class DeviceWorker(BaseWorker):
    def run(self) -> None:
        self.start()
        self.notify("Device worker started", "info")

        connected = False
        offline_error_active = False  # tracks whether we've already raised the error

        while not self.should_stop():
            cmd, payload = self.pop_command(timeout=0.2)

            # control plane
            if cmd == "__stop__":  # internal stop mechanism use to wake the command queue if blocked on get()
                break

            # domain plane
            if cmd == Commands.CONNECT:
                self.log.info("connect requested")
                self.emit_patch("device_status", "Connecting...")
                time.sleep(0.5)
                connected = True
                self.set_connected(True)
                self.emit_patch("device_status", "Connected")
                self.notify("Device connected", "positive")

            elif cmd == Commands.DISCONNECT:
                self.log.info("disconnect requested")
                connected = False
                self.set_connected(False)
                self.emit_patch("device_status", "Disconnected")
                self.notify("Device disconnected", "warning")

            elif cmd == Commands.TRIGGER:
                self.log.info("trigger requested")

            # --- simulated health check (replace with your real logic) ---
            # Imagine: if connected but no heartbeat for X seconds => offline
            if connected:
                heartbeat_ok = True  # TODO: replace with real check
            else:
                heartbeat_ok = True  # if not connected, you may not want to raise "offline" at all

            # --- emit active error when condition becomes bad ---
            if connected and not heartbeat_ok and not offline_error_active:
                offline_error_active = True
                self.emit_error(
                    error_id="device:camera01:offline",
                    source="device",
                    message="Camera 01 is offline",
                    details="No heartbeat for 30 seconds",
                )

            # --- resolve when condition becomes good again ---
            if offline_error_active and (not connected or heartbeat_ok):
                offline_error_active = False
                self.emit_error_resolved(error_id="device:camera01:offline")

            # --- normal periodic updates ---
            if connected:
                self.emit_patch("device_last_seen", time.strftime("%H:%M:%S"))
            time.sleep(2.0)

        self.set_connected(False)
        self.mark_stopped()


def device_worker(
    bridge: UiBridge,
    worker_bus: WorkerBus,
    commands: "queue.Queue[tuple[str, dict]]",
    stop: threading.Event,
    send_cmd: SendCmdFn
) -> None:
    DeviceWorker(
        name="DeviceWorker",
        bridge=bridge,
        worker_bus=worker_bus,
        commands=commands,
        stop=stop,
        send_cmd=send_cmd,
    ).run()
