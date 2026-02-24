from __future__ import annotations

import queue
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from loguru import logger

from services.ui_bridge import UiBridge
from services.worker_bus import BusMessage, WorkerBus
from services.worker_commands import ScriptWorkerCommands as Commands
from services.worker_topics import WorkerTopics as Topics
from services.workers.stepchain.context import StepChainContext
from services.workers.stepchain.loader import ScriptLoader


@dataclass
class ChainInstance:
    script_name: str
    instance_id: str
    context: StepChainContext
    fn: Callable[[Any], None]
    active: bool = True
    paused: bool = False
    next_tick_ts: float = 0.0
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: Optional[threading.Thread] = None


class ScriptRuntime:
    """Central script engine service (application-owned, not a worker)."""

    def __init__(
        self,
        *,
        name: str,
        bridge: UiBridge,
        worker_bus: WorkerBus,
        send_cmd: Callable[[str, str, dict[str, Any]], None],
        scripts_dir: str = "scripts",
        reload_check_interval: float = 1.0,
    ) -> None:
        self.name = name
        self.bridge = bridge
        self.worker_bus = worker_bus
        self.send_cmd = send_cmd
        self.commands: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue()
        self.stop_event = threading.Event()
        self.log = logger.bind(component="ScriptRuntime", service=name)

        self.scripts_dir = str(scripts_dir or "scripts")
        self.loader = ScriptLoader(scripts_dir=self.scripts_dir)

        self.reload_check_interval = float(reload_check_interval or 1.0)
        self.hot_reload_enabled = False
        self.last_reload_check = 0.0

        self.chains: dict[str, ChainInstance] = {}
        self._last_script_sig = ""
        self._last_chain_sig = ""
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_source_id: str = ""

        self.bus_sub = self.worker_bus.subscribe_many([
            Topics.VALUE_CHANGED,
            Topics.CLIENT_CONNECTED,
            Topics.CLIENT_DISCONNECTED,
            Topics.WRITE_FINISHED,
            Topics.WRITE_ERROR,
            Topics.ERROR,
            Topics.TOPIC_MODAL_RESPONSE,
        ])
        self.bus_sub_view_cmd = self.worker_bus.subscribe("view.cmd.*")
        self.ui_state_sub = self.bridge.subscribe_many(["state", "state.*"])

        self.log.info(f"[init] - runtime_initialized - scripts_dir={self.scripts_dir}")

    def _format_exc(self) -> str:
        try:
            return traceback.format_exc()
        except Exception:
            return "<traceback unavailable>"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="script-runtime")
        self._thread.start()
        self.log.info("[start] - runtime_started")

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.commands.put_nowait(("__stop__", {}))
        except Exception:
            pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._running = False
        self.log.info("[stop] - runtime_stopped")

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def send(self, cmd: str, **payload: Any) -> None:
        self.commands.put((str(cmd), payload))

    @contextmanager
    def as_source(self, source_id: str):
        prev = self._current_source_id
        self._current_source_id = str(source_id or "")
        try:
            yield
        finally:
            self._current_source_id = prev

    def _pub(self, topic: Topics, **payload: Any) -> None:
        if not self._current_source_id:
            self.log.error(f"[publish] - missing_source_id - topic={topic} payload_keys={list(payload.keys())}")
            return
        self.worker_bus.publish(topic=topic, source=self.name, source_id=self._current_source_id, **payload)

    def publish_value_as(self, source_id: str, key: str, value: Any) -> None:
        with self.as_source(source_id):
            self._pub(Topics.VALUE_CHANGED, key=key, value=value)

    def publish_error_as(self, source_id: str, key: Optional[str], action: str, error: str) -> None:
        with self.as_source(source_id):
            self._pub(Topics.ERROR, key=key, action=action, error=error)

    def _build_chain_list_payload(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for chain_key, inst in self.chains.items():
            if not inst.lock.acquire(timeout=0.01):
                continue
            try:
                ctx = inst.context
                items.append({
                    "key": chain_key,
                    "script": inst.script_name,
                    "instance": inst.instance_id,
                    "active": bool(inst.active),
                    "paused": bool(inst.paused),
                    "error_flag": bool(getattr(ctx, "error_flag", False)),
                    "error_message": str(getattr(ctx, "error_message", "") or ""),
                    "step": getattr(ctx, "step", 0),
                    "cycle_count": getattr(ctx, "cycle_count", 0),
                    "step_time": getattr(ctx, "step_time", 0.0),
                })
            finally:
                inst.lock.release()
        return items

    def _publish_scripts_if_changed(self, force: bool = False) -> None:
        scripts = self.loader.list_available_scripts()
        sig = "|".join([str(x) for x in (scripts or [])])
        if force or sig != self._last_script_sig:
            self._last_script_sig = sig
            self.publish_value_as(self.name, Commands.LIST_SCRIPTS, scripts)
            self.log.debug(f"[scripts] - list_updated - count={len(scripts or [])}")

    def _publish_chains_if_changed(self, force: bool = False) -> None:
        payload = self._build_chain_list_payload()
        sig = "|".join([
            "%s:%s:%s:%s:%s:%s:%s:%s"
            % (
                str(x.get("key", "")),
                str(x.get("active", False)),
                str(x.get("paused", False)),
                str(x.get("error_flag", False)),
                str(x.get("error_message", "")),
                str(x.get("step", 0)),
                str(x.get("cycle_count", 0)),
                str(x.get("step_time", 0.0)),
            )
            for x in payload
        ])
        if force or sig != self._last_chain_sig:
            self._last_chain_sig = sig
            self.publish_value_as(self.name, Commands.LIST_CHAINS, payload)

    def _publish_chain_state(self, chain_key: str, ctx: StepChainContext) -> None:
        try:
            raw_state = ctx.get_state()
            safe_state = dict(raw_state) if isinstance(raw_state, dict) else {"state": raw_state}
            safe_state.setdefault("chain_key", chain_key)
            if ":" in chain_key:
                script_name, instance_id = chain_key.split(":", 1)
                safe_state.setdefault("script_name", script_name)
                safe_state.setdefault("instance_id", instance_id)
            inst = self.chains.get(chain_key)
            if inst is not None:
                safe_state["active"] = bool(inst.active)
                safe_state["paused"] = bool(inst.paused)
            safe_state.setdefault("error_flag", bool(getattr(ctx, "error_flag", False)))
            safe_state.setdefault("error_message", str(getattr(ctx, "error_message", "") or ""))
            self.publish_value_as(chain_key, Commands.UPDATE_CHAIN_STATE, safe_state)
        except Exception:
            self.publish_error_as(chain_key, key=chain_key, action="publish_chain_state", error=self._format_exc())

    def _publish_chain_log(self, chain_key: str, message: str, level: str = "info") -> None:
        payload = {"chain_key": chain_key, "step": 0, "step_desc": "", "level": str(level), "message": str(message)}
        inst = self.chains.get(chain_key)
        if inst is not None:
            payload["step"] = int(getattr(inst.context, "step", 0))
            payload["step_desc"] = str(getattr(inst.context, "step_desc", "") or "")
        self.publish_value_as(chain_key, Commands.UPDATE_LOG, payload)

    def _apply_bus_msg_to_ctx(self, ctx: StepChainContext, msg: BusMessage) -> None:
        topic = str(getattr(msg, "topic", "") or "")
        source = getattr(msg, "source", "") or "unknown"
        source_id = getattr(msg, "source_id", "") or ""
        payload = getattr(msg, "payload", None) or {}
        ctx.data.setdefault("bus_last", {})[source_id] = {"topic": topic, "payload": payload, "ts": time.time()}

        if topic == str(Topics.VALUE_CHANGED.value):
            ctx._update_bus_value(source=source, source_id=source_id, payload=payload)
        else:
            ctx.data.setdefault("bus_events", {}).setdefault(source_id, {})[topic] = payload

    def _drain_bus_updates(self, max_items: int) -> None:
        def _drain_queue(q: "queue.Queue[BusMessage]", handle_modal: bool) -> int:
            processed = 0
            for _ in range(max_items):
                try:
                    msg = q.get_nowait()
                except queue.Empty:
                    break
                if handle_modal and str(getattr(msg, "topic", "") or "") == Topics.TOPIC_MODAL_RESPONSE:
                    payload = getattr(msg, "payload", None) or {}
                    inst = self.chains.get(str(payload.get("chain_id") or ""))
                    request_id = payload.get("request_id")
                    if inst and request_id is not None:
                        with inst.lock:
                            inst.context._modal_set_result_for_request(str(request_id), payload.get("result"))
                    continue

                for inst in self.chains.values():
                    if not inst.lock.acquire(blocking=False):
                        continue
                    try:
                        if inst.active:
                            self._apply_bus_msg_to_ctx(inst.context, msg)
                    finally:
                        inst.lock.release()
                processed += 1
            return processed

        processed = _drain_queue(self.bus_sub.queue, handle_modal=True)
        if processed < max_items:
            _drain_queue(self.bus_sub_view_cmd.queue, handle_modal=False)

    def _drain_ui_state_updates(self, max_items: int) -> None:
        for _ in range(max_items):
            try:
                msg = self.ui_state_sub.queue.get_nowait()
            except queue.Empty:
                break
            topic = str(getattr(msg, "topic", "") or "")
            payload = getattr(msg, "payload", None)
            data = payload if isinstance(payload, dict) else {}
            for inst in self.chains.values():
                if not inst.lock.acquire(blocking=False):
                    continue
                try:
                    if not inst.active:
                        continue
                    if topic == "state" and isinstance(data, dict):
                        inst.context._replace_app_state(data)
                    elif topic.startswith("state."):
                        key = topic.split("state.", 1)[1]
                        if key:
                            inst.context._update_app_state(key, data.get(key))
                finally:
                    inst.lock.release()

    def _get_cycle_time_s(self, ctx: StepChainContext) -> float:
        try:
            return max(0.1, float(getattr(ctx, "cycle_time", 0.1) or 0.1))
        except Exception:
            return 0.1

    def _chain_runner(self, chain_key: str, inst: ChainInstance) -> None:
        self.log.info(f"[chain] - started - chain_key={chain_key}")
        while not self.stop_event.is_set() and not self.bridge.stopped() and not inst.stop_event.is_set():
            should_sleep = 0.02
            need_tick = False
            fn = None
            with inst.lock:
                if not inst.active:
                    break
                if inst.paused:
                    now_ts = time.time()
                    if inst.context._step_started_ts <= 0:
                        inst.context._step_started_ts = now_ts
                    inst.context.step_elapsed_s = max(0.0, now_ts - inst.context._step_started_ts)
                else:
                    now = time.time()
                    if not inst.next_tick_ts or now >= inst.next_tick_ts:
                        inst.context.cycle_count = inst.context.cycle_count + 1
                        need_tick = True
                        fn = inst.fn
                    else:
                        should_sleep = max(0.0, min(0.05, inst.next_tick_ts - now))

            if need_tick and fn:
                cycle = int(getattr(inst.context, "cycle_count", 0))
                try:
                    start = time.time()
                    fn(inst.context.public)
                    elapsed_ms = (time.time() - start) * 1000.0
                    with inst.lock:
                        inst.context.step_time = round(elapsed_ms, 2)
                        prev_step = int(getattr(inst.context, "step", 0))
                        next_step = int(getattr(inst.context, "next_step", prev_step))
                        if next_step != prev_step:
                            inst.context._step_started_ts = time.time()
                            inst.context.step_elapsed_s = 0.0
                        inst.context.step = next_step
                        inst.next_tick_ts = time.time() + self._get_cycle_time_s(inst.context)
                        suppress_slow_warn = bool(getattr(inst.context, "_suppress_slow_tick_warning_once", False))
                        inst.context._suppress_slow_tick_warning_once = False
                    if elapsed_ms > 200 and not suppress_slow_warn:
                        self.log.warning(f"[chain] - slow_tick - chain_key={chain_key} duration_ms={elapsed_ms:.2f} cycle={cycle}")
                    self._publish_chain_state(chain_key, inst.context)
                    should_sleep = 0.001
                except Exception:
                    err = self._format_exc()
                    self.log.error(f"[chain] - tick_error - chain_key={chain_key} cycle={cycle}\n{err}")
                    self.publish_error_as(chain_key, key=chain_key, action="chain_tick", error=err)
                    with inst.lock:
                        inst.paused = True
                        inst.context.paused = True
                        inst.context.error_flag = True
                        inst.context.error_message = "StepChain crashed. Please review and press Retry."
                    self._publish_chain_log(chain_key, "chain crashed - paused; operator can retry", level="error")
                    self._publish_chain_state(chain_key, inst.context)
                    self._publish_chains_if_changed(True)
                    try:
                        self.bridge.emit_notify(f"⚠️ Script '{chain_key}' crashed. Open Scripts Lab and press Retry.", "warning")
                    except Exception:
                        pass
                    should_sleep = 0.05
            time.sleep(should_sleep)
        self.log.info(f"[chain] - stopped - chain_key={chain_key}")

    def _run_loop(self) -> None:
        handlers = {
            Commands.SET_HOT_RELOAD: self._cmd_set_hot_reload,
            Commands.LIST_SCRIPTS: self._cmd_list_scripts,
            Commands.LIST_CHAINS: self._cmd_list_chains,
            Commands.START_CHAIN: self._cmd_start_chain,
            Commands.STOP_CHAIN: self._cmd_stop_chain,
            Commands.PAUSE_CHAIN: self._cmd_pause_chain,
            Commands.RESUME_CHAIN: self._cmd_resume_chain,
            Commands.RETRY_CHAIN: self._cmd_retry_chain,
            Commands.RELOAD_SCRIPT: self._cmd_reload_script,
            Commands.RELOAD_ALL: self._cmd_reload_all,
        }
        self._publish_scripts_if_changed(True)
        self._publish_chains_if_changed(True)
        try:
            self.bridge.request_ui_state()
        except Exception:
            pass

        try:
            while not self.stop_event.is_set() and not self.bridge.stopped():
                now = time.time()
                if self.hot_reload_enabled and self.reload_check_interval > 0 and (now - self.last_reload_check) >= self.reload_check_interval:
                    self.last_reload_check = now
                    try:
                        reloaded = self.loader.check_for_updates()
                        names = [str(x) for x in reloaded] if isinstance(reloaded, (list, tuple, set)) else []
                        if reloaded is True:
                            names = [str(x) for x in (self.loader.list_available_scripts() or [])]
                        if names:
                            self._apply_reloaded_scripts(names)
                            self._publish_scripts_if_changed(True)
                    except Exception:
                        self.publish_error_as(self.name, key=self.name, action="hot_reload", error=self._format_exc())

                self._drain_bus_updates(400)
                self._drain_ui_state_updates(200)
                self._dispatch_commands(handlers, limit=200)
                self._publish_chains_if_changed(False)
                time.sleep(0.05)
        finally:
            for chain_key in list(self.chains.keys()):
                self._stop_chain(chain_key, "runtime_shutdown")
            self.bus_sub.close()
            self.bus_sub_view_cmd.close()
            self.ui_state_sub.close()
            self._running = False
            self.log.info("[loop] - stopped")

    def _dispatch_commands(self, handlers: dict[str, Callable[[dict[str, Any]], None]], limit: int = 50) -> None:
        for _ in range(limit):
            try:
                cmd, payload = self.commands.get_nowait()
            except queue.Empty:
                return
            if str(cmd) == "__stop__":
                return
            handler = handlers.get(str(cmd))
            if not handler:
                self.log.debug(f"[command] - ignored_unknown - cmd={cmd}")
                continue
            try:
                handler(payload or {})
            except Exception:
                self.publish_error_as(self.name, key=self.name, action=f"cmd:{cmd}", error=self._format_exc())

    def _resolve_chain_key(self, payload: dict[str, Any]) -> str:
        ck = payload.get("chain_key") or payload.get("key")
        if ck:
            return str(ck)
        script_name = payload.get("script") or payload.get("script_name")
        instance_id = payload.get("instance_id") or payload.get("id") or "default"
        if not script_name:
            return ""
        return f"{script_name}:{instance_id}"

    def _cmd_set_hot_reload(self, payload: dict[str, Any]) -> None:
        self.hot_reload_enabled = bool(payload.get("enabled", False))
        if "interval" in payload:
            try:
                interval = float(payload.get("interval", self.reload_check_interval))
                if interval > 0:
                    self.reload_check_interval = interval
            except Exception:
                pass
        self.log.info(f"[hot_reload] - updated enabled={self.hot_reload_enabled} interval_s={self.reload_check_interval}")

    def _cmd_list_scripts(self, payload: dict[str, Any]) -> None:
        self._publish_scripts_if_changed(True)

    def _cmd_list_chains(self, payload: dict[str, Any]) -> None:
        self._publish_chains_if_changed(True)

    def _cmd_start_chain(self, payload: dict[str, Any]) -> None:
        script_name = payload.get("script") or payload.get("script_name")
        instance_id = payload.get("instance_id") or payload.get("id") or "default"
        if not script_name:
            self.publish_error_as(self.name, key=self.name, action="start_chain", error="missing payload.script/script_name")
            return
        chain_key = f"{script_name}:{instance_id}"
        if chain_key in self.chains:
            self._stop_chain(chain_key, "restart")

        fn = self.loader.load_script(str(script_name))
        if fn is None:
            self.publish_error_as(chain_key, key=chain_key, action="start_chain", error="script not found or no entry function")
            return
        ctx = StepChainContext(chain_id=chain_key, worker_bus=self.worker_bus, bridge=self.bridge, state=self.bridge, send_cmd=self.send_cmd)
        inst = ChainInstance(script_name=str(script_name), instance_id=str(instance_id), context=ctx, fn=fn)
        self.chains[chain_key] = inst
        inst.thread = threading.Thread(target=self._chain_runner, args=(chain_key, inst), daemon=True, name=f"chain:{chain_key}")
        inst.thread.start()
        self.log.info(f"[chain] - created - chain_key={chain_key}")
        self._publish_chain_log(chain_key, "chain started", level="info")
        self._publish_chains_if_changed(True)
        self._publish_chain_state(chain_key, ctx)

    def _cmd_stop_chain(self, payload: dict[str, Any]) -> None:
        chain_key = self._resolve_chain_key(payload)
        if not chain_key:
            self.publish_error_as(self.name, key=self.name, action="stop_chain", error="missing payload.chain_key or payload.script/script_name")
            return
        self._stop_chain(chain_key, "stop_command")

    def _cmd_pause_chain(self, payload: dict[str, Any]) -> None:
        chain_key = self._resolve_chain_key(payload)
        inst = self.chains.get(chain_key)
        if not inst:
            self.publish_error_as(chain_key, key=chain_key, action="pause_chain", error="chain not running")
            return
        with inst.lock:
            inst.paused = True
            inst.context.paused = True
        self._publish_chain_log(chain_key, "chain paused", level="info")
        self._publish_chains_if_changed(True)
        self._publish_chain_state(chain_key, inst.context)

    def _cmd_resume_chain(self, payload: dict[str, Any]) -> None:
        chain_key = self._resolve_chain_key(payload)
        inst = self.chains.get(chain_key)
        if not inst:
            self.publish_error_as(chain_key, key=chain_key, action="resume_chain", error="chain not running")
            return
        with inst.lock:
            inst.paused = False
            inst.context.paused = False
            inst.next_tick_ts = 0.0
        self._publish_chain_log(chain_key, "chain resumed", level="info")
        self._publish_chains_if_changed(True)
        self._publish_chain_state(chain_key, inst.context)

    def _cmd_retry_chain(self, payload: dict[str, Any]) -> None:
        chain_key = self._resolve_chain_key(payload)
        inst = self.chains.get(chain_key)
        if not inst:
            self.publish_error_as(chain_key, key=chain_key, action="retry_chain", error="chain not running")
            return
        with inst.lock:
            inst.context.error_flag = False
            inst.context.error_message = ""
            inst.paused = False
            inst.context.paused = False
            inst.next_tick_ts = 0.0
        self._publish_chain_log(chain_key, "retry requested by operator", level="info")
        self._publish_chains_if_changed(True)
        self._publish_chain_state(chain_key, inst.context)

    def _apply_reloaded_scripts(self, script_names: list[str]) -> None:
        for chain_key, inst in self.chains.items():
            if inst.active and inst.script_name in script_names:
                fn = self.loader.load_script(inst.script_name, force=True)
                if fn:
                    with inst.lock:
                        inst.fn = fn
                    self.log.info(f"[reload] - chain_handler_swapped - chain_key={chain_key}")

    def _cmd_reload_script(self, payload: dict[str, Any]) -> None:
        script_name = payload.get("script") or payload.get("script_name")
        if not script_name:
            self.publish_error_as(self.name, key=self.name, action="reload_script", error="missing payload.script/script_name")
            return
        fn = self.loader.load_script(str(script_name), force=True)
        if fn:
            self._apply_reloaded_scripts([str(script_name)])
        self._publish_scripts_if_changed(True)

    def _cmd_reload_all(self, payload: dict[str, Any]) -> None:
        scripts = [str(x) for x in (self.loader.list_available_scripts() or [])]
        reloaded: list[str] = []
        for s in scripts:
            fn = self.loader.load_script(s, force=True)
            if fn:
                reloaded.append(s)
        if reloaded:
            self._apply_reloaded_scripts(reloaded)
        self._publish_scripts_if_changed(True)
        self._publish_chains_if_changed(True)

    def _stop_chain(self, chain_key: str, reason: str) -> None:
        inst = self.chains.get(chain_key)
        if not inst:
            return
        with inst.lock:
            inst.active = False
            inst.stop_event.set()
        if inst.thread and inst.thread.is_alive():
            inst.thread.join(timeout=1.0)
        self.chains.pop(chain_key, None)
        self.log.info(f"[chain] - removed - chain_key={chain_key} reason={reason}")
        self._publish_chain_log(chain_key, f"chain stopped: {reason}", level="info")
        self._publish_chains_if_changed(True)
