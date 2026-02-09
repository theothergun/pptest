# services/workers/script_worker.py
from __future__ import annotations

import time
import threading
import queue
from dataclasses import dataclass
from typing import Any, Callable

from services.workers.base_worker import BaseWorker
from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_commands import ScriptWorkerCommands as Commands
from services.worker_topics import WorkerTopics as Topics

from services.workers.stepchain.context import StepChainContext
from services.workers.stepchain.loader import ScriptLoader


KEY_SCRIPTS_LIST = "script.scripts_list"
KEY_CHAINS_LIST = "script.chains_list"
KEY_CHAIN_STATE = "script.chain_state"
KEY_LOG = "script.log"


@dataclass
class ChainInstance:
	script_name: str
	instance_id: str
	context: StepChainContext
	fn: Callable[[StepChainContext], None]
	active: bool = True
	paused: bool = False


class ScriptWorker(BaseWorker):
	def __init__(
		self,
		name: str,
		bridge: UiBridge,
		worker_bus: WorkerBus,
		commands: "queue.Queue[tuple[str, dict[str, Any]]]",
		stop: threading.Event,
		send_cmd,
	) -> None:
		super(ScriptWorker, self).__init__(
			name=name,
			bridge=bridge,
			worker_bus=worker_bus,
			commands=commands,
			stop=stop,
			send_cmd=send_cmd,
		)

		self.loader = ScriptLoader(scripts_dir="scripts")
		self.chains: dict[str, ChainInstance] = {}

		self.last_reload_check = time.time()
		self.reload_check_interval = 1.0

		self._last_scripts: list[str] = []
		self._last_chain_sig = ""

		self.ui_state_sub = bridge.subscribe_many(["state", "state.*"])
		self.ui_state = bridge

		self.bus_sub = worker_bus.subscribe_many([
			Topics.VALUE_CHANGED,
			Topics.CLIENT_CONNECTED,
			Topics.CLIENT_DISCONNECTED,
			Topics.WRITE_FINISHED,
			Topics.WRITE_ERROR,
			Topics.ERROR,
		])

	# ------------------------------------------------------------------ snapshots

	def _get_scripts_list(self) -> list[str]:
		try:
			return sorted(self.loader.list_available_scripts())
		except Exception:
			return []

	def _publish_scripts_if_changed(self, force: bool) -> None:
		scripts = self._get_scripts_list()
		if force or scripts != self._last_scripts:
			self._last_scripts = list(scripts)
			self.current_source_id = "script_worker"
			self.publish_value(KEY_SCRIPTS_LIST, list(scripts))

	def _build_chain_list(self) -> list[dict[str, Any]]:
		items: list[dict[str, Any]] = []
		for key, inst in sorted(self.chains.items()):
			items.append({
				"key": key,
				"script": inst.script_name,
				"instance": inst.instance_id,
				"active": inst.active,
				"paused": inst.paused,
				"step": getattr(inst.context, "step", 0),
				"cycle_count": getattr(inst.context, "cycle_count", 0),
			})
		return items

	def _publish_chains_if_changed(self, force: bool) -> None:
		lst = self._build_chain_list()

		sig_parts: list[str] = []
		for x in lst:
			sig_parts.append("%s:%s:%s:%s:%s" % (
				x.get("key"),
				int(bool(x.get("active"))),
				int(bool(x.get("paused"))),
				int(x.get("step") or 0),
				int(x.get("cycle_count") or 0),
			))
		sig = "|".join(sig_parts)

		if force or sig != self._last_chain_sig:
			self._last_chain_sig = sig
			self.current_source_id = "script_worker"
			self.publish_value(KEY_CHAINS_LIST, lst)

	def _stop_chain(self, chain_key: str, reason: str) -> None:
		inst = self.chains.get(chain_key)
		if not inst or not inst.active:
			return

		inst.active = False

		try:
			close_fn = getattr(inst.context, "close", None)
			if callable(close_fn):
				close_fn()
		except Exception:
			pass

		self.log.info("[_stop_chain] - stopped - chain_key=%s reason=%s" % (chain_key, reason))
		self._publish_chains_if_changed(True)

	# ------------------------------------------------------------------ bus -> ctx.data

	def _apply_bus_msg_to_ctx(self, ctx: StepChainContext, msg: Any) -> None:
		now = time.time()
		topic = getattr(msg, "topic", None)
		payload = getattr(msg, "payload", None) or {}
		source_id = getattr(msg, "source_id", "") or ""

		client_id = payload.get("client_id") or source_id or ""

		try:
			if "bus_values" not in ctx.data:
				ctx.data["bus_values"] = {}
			if "bus_events" not in ctx.data:
				ctx.data["bus_events"] = {}
			if "bus_last" not in ctx.data:
				ctx.data["bus_last"] = {}

			if topic == Topics.VALUE_CHANGED:
				key = payload.get("key")
				if key:
					if client_id not in ctx.data["bus_values"]:
						ctx.data["bus_values"][client_id] = {}
					ctx.data["bus_values"][client_id][key] = payload.get("value")
			else:
				if client_id not in ctx.data["bus_events"]:
					ctx.data["bus_events"][client_id] = {}
				ctx.data["bus_events"][client_id][str(topic or "")] = payload

			ctx.data["bus_last"][client_id] = {"topic": str(topic or ""), "payload": payload, "ts": now}
		except Exception as ex:
			self.log.error("[_apply_bus_msg_to_ctx] - failed - error=%s" % str(ex))

	def _drain_bus_updates(self, max_items: int) -> None:
		for _ in range(max_items):
			try:
				msg = self.bus_sub.queue.get_nowait()
			except queue.Empty:
				break

			for inst in self.chains.values():
				if not inst.active:
					continue
				self._apply_bus_msg_to_ctx(inst.context, msg)

	# ------------------------------------------------------------------ lifecycle

	def run(self) -> None:
		self.log.info("[run] - started")

		self._publish_scripts_if_changed(True)
		self._publish_chains_if_changed(True)

		while not self.stop_event.is_set():
			now = time.time()

			if (now - self.last_reload_check) >= self.reload_check_interval:
				self.last_reload_check = now
				try:
					self.loader.reload_all()
					self._publish_scripts_if_changed(True)
				except Exception as ex:
					# FIX: publish_error requires key
					self.publish_error(key="script_worker", action="reload", error=str(ex))

			self._drain_bus_updates(400)

			self._process_commands()

			any_chain_changed = False
			for chain_key, inst in list(self.chains.items()):
				if not inst.active or inst.paused:
					continue

				prev_step = getattr(inst.context, "step", None)
				prev_cycle = getattr(inst.context, "cycle_count", None)

				try:
					inst.fn(inst.context)
				except Exception as ex:
					self.log.error("[run] - chain crashed - chain_key=%s error=%s" % (chain_key, str(ex)))
					self.publish_error(key=chain_key, action="chain_tick", error=str(ex))
					self._stop_chain(chain_key, "exception")
					continue

				try:
					get_state = getattr(inst.context, "get_state_dict", None)
					if callable(get_state):
						self.current_source_id = chain_key
						self.publish_value(KEY_CHAIN_STATE, {
							"chain_key": chain_key,
							"state": get_state(),
						})
				except Exception as ex:
					self.publish_error(key=chain_key, action="publish_chain_state", error=str(ex))

				if getattr(inst.context, "step", None) != prev_step or getattr(inst.context, "cycle_count", None) != prev_cycle:
					any_chain_changed = True

			if any_chain_changed:
				self._publish_chains_if_changed(True)

			time.sleep(0.01)

		try:
			self.bus_sub.close()
		except Exception:
			pass
		try:
			self.ui_state_sub.close()
		except Exception:
			pass

		self.log.info("[run] - stopped")

	def _process_commands(self) -> None:
		while True:
			try:
				cmd, payload = self.commands.get_nowait()
				self.loader.check_for_updates()
				self._publish_chains_if_changed(True)
			except queue.Empty:
				break

			if cmd == "__stop__":
				return

			action = str(cmd or "")
			payload = payload or {}

			if action == str(Commands.RELOAD_ALL):
				try:
					self.loader.reload_all()
					self._publish_scripts_if_changed(True)
				except Exception as ex:
					self.publish_error(key="script_worker", action="reload_all", error=str(ex))

			elif action == str(Commands.LIST_SCRIPTS):
				self._publish_scripts_if_changed(True)

			elif action == str(Commands.LIST_CHAINS):
				self._publish_chains_if_changed(True)

			elif action == str(Commands.START_CHAIN):
				script_name = payload.get("script")
				instance_id = payload.get("instance_id") or str(int(time.time() * 1000))
				if not script_name:
					self.publish_error(key="script_worker", action="start_chain", error="missing payload.script")
					continue

				try:

					self.loader.load_script(script_name)
					fn = self.loader.get_entrypoint(script_name)
				except Exception as ex:
					self.publish_error(key=str(script_name), action="start_chain", error=str(ex))
					continue

				chain_key = "%s:%s" % (script_name, instance_id)

				try:
					ctx = StepChainContext(
						chain_id=chain_key,
						worker_bus=self.worker_bus,
						bridge=self.bridge,
						state=self.ui_state,
					)
				except Exception as ex:
					self.publish_error(key=chain_key, action="create_ctx", error=str(ex))
					continue

				self.chains[chain_key] = ChainInstance(
					script_name=str(script_name),
					instance_id=str(instance_id),
					context=ctx,
					fn=fn,
					active=True,
					paused=False,
				)

				self._publish_chains_if_changed(True)

			elif action == str(Commands.STOP_CHAIN):
				chain_key = payload.get("chain_key")
				if chain_key:
					self._stop_chain(str(chain_key), "cmd")

			elif action == str(Commands.PAUSE_CHAIN):
				chain_key = payload.get("chain_key")
				inst = self.chains.get(str(chain_key or ""))
				if inst:
					inst.paused = True
					self._publish_chains_if_changed(True)

			elif action == str(Commands.RESUME_CHAIN):
				chain_key = payload.get("chain_key")
				inst = self.chains.get(str(chain_key or ""))
				if inst:
					inst.paused = False
					self._publish_chains_if_changed(True)
