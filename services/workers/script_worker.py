# services/workers/script_worker.py
from __future__ import annotations

import time
import queue
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from loguru import logger

from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus, BusMessage
from services.workers.base_worker import BaseWorker
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


class ScriptWorker(BaseWorker):
	def __init__(
		self,
		name: str,
		bridge: UiBridge,
		worker_bus: WorkerBus,
		commands: "queue.Queue[tuple[str, dict[str, Any]]]",
		stop: Any,
		send_cmd: Any,
		scripts_dir: str = "scripts",
		reload_check_interval: float = 1.0,
	) -> None:
		super(ScriptWorker, self).__init__(
			name=name,
			bridge=bridge,
			worker_bus=worker_bus,
			commands=commands,
			stop=stop,
			send_cmd=send_cmd,
		)

		self.scripts_dir = str(scripts_dir or "scripts")
		self.loader = ScriptLoader(scripts_dir=self.scripts_dir)

		self.reload_check_interval = float(reload_check_interval or 1.0)
		self.hot_reload_enabled = False
		self.last_reload_check = 0.0

		self.chains: dict[str, ChainInstance] = {}
		self._last_script_sig = ""
		self._last_chain_sig = ""

		self.bus_sub = self.add_subscription(self.worker_bus.subscribe_many([
			Topics.VALUE_CHANGED,
			Topics.CLIENT_CONNECTED,
			Topics.CLIENT_DISCONNECTED,
			Topics.WRITE_FINISHED,
			Topics.WRITE_ERROR,
			Topics.ERROR,
			Topics.TOPIC_MODAL_RESPONSE,
		]))
		self.bus_sub_view_cmd = self.add_subscription(self.worker_bus.subscribe("view.cmd.*"))



		# Mirror UI/AppState updates into each chain context so scripts can read state.* values.
		self.ui_state_sub = self.add_subscription(self.bridge.subscribe_many(["state", "state.*"]))

		self.log.info(f"[__init__] init scripts_dir={self.scripts_dir}")

	# ------------------------------------------------------------------ safe helpers
	def _format_exc(self) -> str:
		try:
			return traceback.format_exc()
		except Exception:
			return "<traceback unavailable>"

	# ------------------------------------------------------------------ publishing

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
			self.publish_value_as("script_worker", Commands.LIST_SCRIPTS, scripts)

	def _publish_chains_if_changed(self, force: bool = False) -> None:
		payload = self._build_chain_list_payload()
		sig = "|".join([
			"%s:%s:%s:%s:%s:%s:%s:%s" % (
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
			self.publish_value_as("script_worker", Commands.LIST_CHAINS, payload)

	def _publish_chain_state(self, chain_key: str, ctx: StepChainContext) -> None:
		"""
		MUST NOT crash the worker if ctx.get_state() contains cycles / deep structures.
		"""
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
			err = "failed publishing chain state\n%s" % self._format_exc()
			self.publish_error_as(chain_key, key=chain_key, action="publish_chain_state", error=err)

	def _publish_chain_log(self, chain_key: str, message: str, level: str = "info") -> None:
		try:
			payload = {"chain_key": chain_key, "step": 0, "step_desc": "", "level": str(level), "message": str(message)}
			inst = self.chains.get(chain_key)
			if inst is not None:
				payload["step"] = int(getattr(inst.context, "step", 0))
				payload["step_desc"] = str(getattr(inst.context, "step_desc", "") or "")
			self.publish_value_as(chain_key, Commands.UPDATE_LOG, payload)
		except Exception:
			err = "failed publishing chain log\n%s" % self._format_exc()
			self.publish_error_as(chain_key, key=chain_key, action="publish_chain_log", error=err)

	# ------------------------------------------------------------------ bus mapping

	def _expected_topic_value_changed(self) -> str:
		return str(getattr(Topics.VALUE_CHANGED, "value", str(Topics.VALUE_CHANGED)))

	def _apply_bus_msg_to_ctx(self, ctx: StepChainContext, msg: BusMessage) -> None:
		try:
			topic = str(getattr(msg, "topic", "") or "")
			source = getattr(msg, "source", "") or "unknown"
			source_id = getattr(msg, "source_id", "") or ""
			payload = getattr(msg, "payload", None) or {}

			if "bus_last" not in ctx.data:
				ctx.data["bus_last"] = {}
			ctx.data["bus_last"][source_id] = {
				"topic": topic,
				"payload": payload,
				"ts": time.time(),
			}

			if topic == self._expected_topic_value_changed():
				ctx._update_bus_value(source=source, source_id=source_id, payload=payload)
			else:
				if "bus_events" not in ctx.data:
					ctx.data["bus_events"] = {}
				if source_id not in ctx.data["bus_events"]:
					ctx.data["bus_events"][source_id] = {}
				ctx.data["bus_events"][source_id][topic] = payload

		except Exception:
			self.log.error("[_apply_bus_msg_to_ctx] failed\n%s" % self._format_exc())

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
					request_id = payload.get("request_id")
					chain_id = payload.get("chain_id")
					result = payload.get("result")

					inst = self.chains.get(str(chain_id or ""))
					if inst and request_id is not None:
						with inst.lock:
							inst.context._modal_set_result_for_request(str(request_id), result)
					continue

				for inst in self.chains.values():
					if not inst.lock.acquire(blocking=False):
						continue
					try:
						if not inst.active:
							continue
						self._apply_bus_msg_to_ctx(inst.context, msg)
					finally:
						inst.lock.release()
				processed += 1
			return processed

		processed = _drain_queue(self.bus_sub.queue, handle_modal=True)
		if processed < max_items:
			_drain_queue(self.bus_sub_view_cmd.queue, handle_modal=False)

	def _apply_ui_state_msg_to_ctx(self, ctx: StepChainContext, topic: str, payload: dict[str, Any]) -> None:
		try:
			if topic == "state":
				if isinstance(payload, dict):
					ctx._replace_app_state(payload)
				return

			if not topic.startswith("state."):
				return

			key = topic.split("state.", 1)[1]
			if not key:
				return

			value = payload.get(key) if isinstance(payload, dict) else None
			ctx._update_app_state(key, value)
		except Exception:
			self.log.error("[_apply_ui_state_msg_to_ctx] failed\n%s" % self._format_exc())

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
					self._apply_ui_state_msg_to_ctx(inst.context, topic, data)
				finally:
					inst.lock.release()

	# ------------------------------------------------------------------ lifecycle

	def _get_cycle_time_s(self, ctx: StepChainContext) -> float:
		try:
			v = getattr(ctx, "cycle_time", None)
			if v is None:
				return 0.1
			vf = float(v)
			if vf <= 0:
				return 0.1
			return vf
		except Exception:
			return 0.1

	def _normalize_reloaded(self, reloaded: Any) -> list[str]:
		if reloaded is None or reloaded is False:
			return []
		if isinstance(reloaded, (list, tuple, set)):
			return [str(x) for x in reloaded if x]
		if reloaded is True:
			try:
				return [str(x) for x in (self.loader.list_available_scripts() or [])]
			except Exception:
				return []
		return []

	def _chain_runner(self, chain_key: str, inst: ChainInstance) -> None:
		self.log.info(f"[_chain_runner] started chain_key={chain_key}")
		while not self.should_stop() and not inst.stop_event.is_set():
			should_sleep = 0.02
			should_publish_changed = False
			notify_text = ""
			with inst.lock:
				if not inst.active:
					break

				if inst.paused:
					now_ts = time.time()
					if inst.context._step_started_ts <= 0:
						inst.context._step_started_ts = now_ts
					inst.context.step_elapsed_s = max(0.0, now_ts - inst.context._step_started_ts)
					should_sleep = 0.02
					need_tick = False
				else:
					now = time.time()
					if inst.next_tick_ts and now < inst.next_tick_ts:
						should_sleep = max(0.0, min(0.05, inst.next_tick_ts - now))
						need_tick = False
					else:
						inst.context.cycle_count = inst.context.cycle_count + 1
						now_ts = time.time()
						if inst.context._step_started_ts <= 0:
							inst.context._step_started_ts = now_ts
						inst.context.step_elapsed_s = max(0.0, now_ts - inst.context._step_started_ts)
						fn = inst.fn
						need_tick = True

			if need_tick:
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
						cycle_s = self._get_cycle_time_s(inst.context)
						inst.next_tick_ts = time.time() + cycle_s
					should_sleep = 0.001
					self._publish_chain_state(chain_key, inst.context)
				except Exception:
					err = "chain crashed chain_key=%s\n%s" % (chain_key, self._format_exc())
					self.log.error("[_chain_runner] %s" % err)
					self.publish_error_as(chain_key, key=chain_key, action="chain_tick", error=err)
					with inst.lock:
						inst.paused = True
						inst.context.paused = True
						inst.context.error_flag = True
						inst.context.error_message = "StepChain crashed. Please review and press Retry."
					self._publish_chain_log(chain_key, "chain crashed - paused; operator can retry", level="error")
					self._publish_chain_state(chain_key, inst.context)
					should_publish_changed = True
					notify_text = "⚠️ Script '%s' crashed. Open Scripts Lab and press Retry." % chain_key
					should_sleep = 0.05

			if should_publish_changed:
				self._publish_chains_if_changed(True)
				if notify_text:
					try:
						self.bridge.emit_notify(notify_text, "warning")
					except Exception:
						pass

			if should_sleep > 0:
				time.sleep(should_sleep)

		self.log.info(f"[_chain_runner] stopped chain_key={chain_key}")

	def run(self) -> None:
		self.start()
		self.log.info("[run] started")

		self._publish_scripts_if_changed(True)
		self._publish_chains_if_changed(True)
		try:
			self.bridge.request_ui_state()
		except Exception:
			pass

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

		try:
			while not self.should_stop():
				now = time.time()

				# hot reload
				if self.hot_reload_enabled and self.reload_check_interval > 0:
					if (now - self.last_reload_check) >= self.reload_check_interval:
						self.last_reload_check = now
						try:
							reloaded_raw = self.loader.check_for_updates()
							reloaded = self._normalize_reloaded(reloaded_raw)
							if reloaded:
								self._apply_reloaded_scripts(reloaded)
								self._publish_scripts_if_changed(True)
						except Exception:
							err = "hot reload failed\n%s" % self._format_exc()
							self.publish_error_as("script_worker", key="script_worker", action="hot_reload", error=err)

				self._drain_bus_updates(400)
				self._drain_ui_state_updates(200)
				self.dispatch_commands(handlers, limit=200, unknown_handler=self._cmd_unknown)

				# Update UI once per loop while chain ticks run in per-chain threads
				self._publish_chains_if_changed(False)
				time.sleep(0.05)

		except Exception:
			logger.error(self._format_exc())
		finally:
			for chain_key in list(self.chains.keys()):
				self._stop_chain(chain_key, "worker_shutdown")
			self.close_subscriptions()
			self.mark_stopped()
			self.log.info("[run] stopped")

	# ------------------------------------------------------------------ command handlers

	def _cmd_unknown(self, payload: dict[str, Any]) -> None:
		self.log.debug(f"unknown command ignored payload={payload!r}")

	def _cmd_set_hot_reload(self, payload: dict[str, Any]) -> None:
		self.hot_reload_enabled = bool(payload.get("enabled", False))
		if "interval" in payload:
			try:
				new_interval = float(payload.get("interval", self.reload_check_interval))
				if new_interval > 0:
					self.reload_check_interval = new_interval
			except Exception:
				pass
		self.log.info(f"[_cmd_set_hot_reload] enabled={self.hot_reload_enabled} interval={self.reload_check_interval}")

	def _cmd_list_scripts(self, payload: dict[str, Any]) -> None:
		self._publish_scripts_if_changed(True)

	def _cmd_list_chains(self, payload: dict[str, Any]) -> None:
		self._publish_chains_if_changed(True)

	def _cmd_start_chain(self, payload: dict[str, Any]) -> None:
		script_name = payload.get("script") or payload.get("script_name")
		instance_id = payload.get("instance_id") or payload.get("id") or "default"
		if not script_name:
			self.publish_error_as("script_worker", key="script_worker", action="start_chain", error="missing payload.script/script_name")
			return

		script_name = str(script_name)
		instance_id = str(instance_id)
		chain_key = f"{script_name}:{instance_id}"

		if chain_key in self.chains:
			self._stop_chain(chain_key, "restart")

		try:
			fn = self.loader.load_script(script_name)
			if fn is None:
				self.publish_error_as(chain_key, key=chain_key, action="start_chain", error="script not found or no entry function")
				return
		except Exception:
			err = "load_script failed\n%s" % self._format_exc()
			self.publish_error_as(chain_key, key=chain_key, action="start_chain", error=err)
			return

		try:
			ctx = StepChainContext(
				chain_id=chain_key,
				worker_bus=self.worker_bus,
				bridge=self.bridge,
				state=self.bridge,
				send_cmd=self.send_cmd,
			)
		except Exception:
			err = "StepChainContext init failed\n%s" % self._format_exc()
			self.publish_error_as(chain_key, key=chain_key, action="start_chain", error=err)
			return

		inst = ChainInstance(
			script_name=script_name,
			instance_id=instance_id,
			context=ctx,
			fn=fn,
			active=True,
			paused=False,
			next_tick_ts=0.0,
		)
		self.chains[chain_key] = inst
		inst.thread = threading.Thread(
			target=self._chain_runner,
			args=(chain_key, inst),
			daemon=True,
			name=f"chain:{chain_key}",
		)
		inst.thread.start()

		self.log.info(f"[_cmd_start_chain] started chain_key={chain_key} thread={inst.thread.name}")
		self._publish_chain_log(chain_key, "chain started", level="info")
		self._publish_chains_if_changed(True)
		self._publish_chain_state(chain_key, ctx)

	def _resolve_chain_key(self, payload: dict[str, Any]) -> str:
		ck = payload.get("chain_key") or payload.get("key")
		if ck:
			return str(ck)

		script_name = payload.get("script") or payload.get("script_name")
		instance_id = payload.get("instance_id") or payload.get("id") or "default"
		if not script_name:
			return ""
		return f"{script_name}:{instance_id}"

	def _cmd_stop_chain(self, payload: dict[str, Any]) -> None:
		chain_key = self._resolve_chain_key(payload)
		if not chain_key:
			self.publish_error_as("script_worker", key="script_worker", action="stop_chain", error="missing payload.chain_key or payload.script/script_name")
			return
		self._stop_chain(chain_key, "stop_command")

	def _cmd_pause_chain(self, payload: dict[str, Any]) -> None:
		chain_key = self._resolve_chain_key(payload)
		if not chain_key:
			self.publish_error_as("script_worker", key="script_worker", action="pause_chain", error="missing payload.chain_key or payload.script/script_name")
			return

		inst = self.chains.get(chain_key)
		if not inst:
			self.publish_error_as(chain_key, key=chain_key, action="pause_chain", error="chain not running")
			return

		with inst.lock:
			inst.paused = True
			inst.context.paused = True
		self.log.info(f"[_cmd_pause_chain] paused chain_key={chain_key}")
		self._publish_chain_log(chain_key, "chain paused", level="info")
		self._publish_chains_if_changed(True)
		self._publish_chain_state(chain_key, inst.context)

	def _cmd_resume_chain(self, payload: dict[str, Any]) -> None:
		chain_key = self._resolve_chain_key(payload)
		if not chain_key:
			self.publish_error_as("script_worker", key="script_worker", action="resume_chain", error="missing payload.chain_key or payload.script/script_name")
			return

		inst = self.chains.get(chain_key)
		if not inst:
			self.publish_error_as(chain_key, key=chain_key, action="resume_chain", error="chain not running")
			return

		with inst.lock:
			inst.paused = False
			inst.context.paused = False
			inst.next_tick_ts = 0.0
		self.log.info(f"[_cmd_resume_chain] resumed chain_key={chain_key}")
		self._publish_chain_log(chain_key, "chain resumed", level="info")
		self._publish_chains_if_changed(True)
		self._publish_chain_state(chain_key, inst.context)

	def _cmd_retry_chain(self, payload: dict[str, Any]) -> None:
		chain_key = self._resolve_chain_key(payload)
		if not chain_key:
			self.publish_error_as("script_worker", key="script_worker", action="retry_chain", error="missing payload.chain_key or payload.script/script_name")
			return

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
		self.log.info(f"[_cmd_retry_chain] retrying chain_key={chain_key}")
		self._publish_chain_log(chain_key, "retry requested by operator", level="info")
		self._publish_chains_if_changed(True)
		self._publish_chain_state(chain_key, inst.context)

	def _apply_reloaded_scripts(self, script_names: list[str]) -> None:
		for chain_key, inst in self.chains.items():
			if not inst.active:
				continue
			if inst.script_name in script_names:
				try:
					fn = self.loader.load_script(inst.script_name, force=True)
					if fn:
						with inst.lock:
							inst.fn = fn
						self.log.info(f"[_apply_reloaded_scripts] updated chain_key={chain_key}")
				except Exception:
					err = "apply_reload failed\n%s" % self._format_exc()
					self.publish_error_as(chain_key, key=chain_key, action="apply_reload", error=err)

	def _cmd_reload_script(self, payload: dict[str, Any]) -> None:
		script_name = payload.get("script") or payload.get("script_name")
		if not script_name:
			self.publish_error_as("script_worker", key="script_worker", action="reload_script", error="missing payload.script/script_name")
			return

		script_name = str(script_name)

		try:
			fn = self.loader.load_script(script_name, force=True)
			if fn:
				self._apply_reloaded_scripts([script_name])
			self._publish_scripts_if_changed(True)
		except Exception:
			err = "reload_script failed\n%s" % self._format_exc()
			self.publish_error_as(f"script:{script_name}", key=f"script:{script_name}", action="reload_script", error=err)


	def _cmd_reload_all(self, payload: dict[str, Any]) -> None:
		try:
			scripts = [str(x) for x in (self.loader.list_available_scripts() or [])]
		except Exception:
			err = "reload_all list scripts failed\n%s" % self._format_exc()
			self.publish_error_as("script_worker", key="script_worker", action="reload_all", error=err)
			return

		reloaded: list[str] = []
		for s in scripts:
			try:
				fn = self.loader.load_script(s, force=True)
				if fn:
					reloaded.append(s)
			except Exception:
				err = "reload_all failed script=%s\n%s" % (s, self._format_exc())
				self.publish_error_as(f"script:{s}", key=f"script:{s}", action="reload_all_script", error=err)

		if reloaded:
			self._apply_reloaded_scripts(reloaded)

		self._publish_scripts_if_changed(True)
		self._publish_chains_if_changed(True)
		try:
			self.bridge.request_ui_state()
		except Exception:
			pass
		self.log.info(f"[_cmd_reload_all] reloaded_count={len(reloaded)}")

	# ------------------------------------------------------------------ internals

	def _stop_chain(self, chain_key: str, reason: str) -> None:
		inst = self.chains.get(chain_key)
		if not inst:
			return

		with inst.lock:
			inst.active = False
			inst.stop_event.set()

		if inst.thread and inst.thread.is_alive():
			inst.thread.join(timeout=1.0)

		try:
			del self.chains[chain_key]
		except Exception:
			pass

		self.log.info(f"[_stop_chain] stopped chain_key={chain_key} reason={reason}")
		self._publish_chain_log(chain_key, "chain stopped: %s" % reason, level="info")
		self._publish_chains_if_changed(True)
