from __future__ import annotations

import fnmatch
import queue
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Optional, Union

from loguru import logger

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus


Cmd = Union[str, StrEnum]
SendCmdFn = Callable[[str, Cmd, dict[str, Any]], None]
WorkerFn = Callable[
    [UiBridge, WorkerBus, "queue.Queue[tuple[str, dict[str, Any]]]", threading.Event, SendCmdFn],
    None,
]


@dataclass
class WorkerHandle:
    name: str
    commands: "queue.Queue[tuple[str, dict[str, Any]]]"
    stop_event: threading.Event
    thread: threading.Thread

    def send(self, cmd: Cmd, **payload: Any) -> None:
        logger.bind(component="WorkerHandle", worker=self.name).debug(
            f"send cmd='{cmd}' payload_keys={list(payload.keys())}"
        )
        self.commands.put((str(cmd), payload))

    def stop(self) -> None:
        logger.bind(component="WorkerHandle", worker=self.name).info("stop requested")
        self.stop_event.set()
        try:
            self.commands.put_nowait(("__stop__", {}))
        except Exception:
            logger.warning("Failed enqueueing __stop__ command for worker '{}'", self.name)

    def is_alive(self) -> bool:
        return self.thread.is_alive()


class WorkerRegistry:
    def __init__(self, bridge: UiBridge, worker_bus: WorkerBus) -> None:
        self.bridge = bridge
        self.worker_bus = worker_bus
        self._workers: dict[str, WorkerHandle] = {}
        self._log = logger.bind(component="WorkerRegistry")
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle


    def start_worker(self, name: str, target) -> WorkerHandle:
        """
            Start a worker if not already running.

            target is now a Worker CLASS (subclass of BaseWorker),
            not a function anymore.
            """
        with self._lock:
            handle = self._workers.get(name)
        if handle and handle.is_alive():
            return handle

        commands: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue()
        stop_event = threading.Event()

        def send_cmd(target_worker: str, cmd: Cmd, payload: dict[str, Any]) -> None:
            with self._lock:
                h = self._workers.get(target_worker)
            if not h:
                return
            h.commands.put((str(cmd), payload))

        def run() -> None:
            wlog = logger.bind(component="Worker", worker=name, thread=threading.current_thread().name)
            wlog.info("thread started")

            try:
                # ⬇️ THIS IS THE IMPORTANT PART
                worker = target(
                    name=name,
                    bridge=self.bridge,
                    worker_bus=self.worker_bus,
                    commands=commands,
                    stop=stop_event,
                    send_cmd=send_cmd,
                )
                worker.run()

                wlog.info("thread exited normally")
            except Exception:
                wlog.exception("thread crashed")
                try:
                    self.bridge.emit_notify(f"Worker '{name}' crashed (see logs)", "error")
                except Exception:
                    wlog.warning("Failed emitting worker crash notification to UI bridge")

        thread = threading.Thread(target=run, daemon=True, name=f"worker:{name}")
        handle = WorkerHandle(name, commands, stop_event, thread)

        with self._lock:
            self._workers[name] = handle

        thread.start()
        self._log.info(f"started worker name='{name}' thread='{thread.name}'")

        return handle

    def stop(self, name: str) -> None:
        with self._lock:
            h = self._workers.get(name)
        if h:
            h.stop()

    def stop_all(self, *, clear_registry: bool = False) -> None:
        self._log.info(f"stop_all requested count={len(self._workers)}")
        for h in list(self._workers.values()):
            try:
                h.stop()
            except Exception:
                self._log.exception(f"failed stopping worker name='{h.name}'")
        if clear_registry:
            self._workers.clear()

    def broadcast_stop(self, pattern: str) -> int:
        with self._lock:
            items = list(self._workers.items())

        count = 0
        for name, h in items:
            if h.is_alive() and fnmatch.fnmatch(name, pattern):
                h.stop()
                count += 1
        return count

    # ------------------------------------------------------------------ commands

    def send_to(self, target_worker: str, cmd: Cmd, **payload: Any) -> None:
        with self._lock:
            h = self._workers.get(target_worker)
        if not h:
            return
        h.commands.put((str(cmd), payload))

    def broadcast_cmd(self, pattern: str, cmd: Cmd, **payload: Any) -> int:
        with self._lock:
            items = list(self._workers.items())

        count = 0
        for name, h in items:
            if h.is_alive() and fnmatch.fnmatch(name, pattern):
                h.commands.put((str(cmd), payload))
                count += 1
        return count

    # ------------------------------------------------------------------ query

    def get(self, name: str) -> Optional[WorkerHandle]:
        with self._lock:
            return self._workers.get(name)

    def is_running(self, name: str) -> bool:
        with self._lock:
            h = self._workers.get(name)
        return bool(h and h.thread.is_alive())

    def list_workers(self, pattern: str = "*") -> list[str]:
        with self._lock:
            items = list(self._workers.items())
        return [name for name, h in items if h.is_alive() and fnmatch.fnmatch(name, pattern)]
