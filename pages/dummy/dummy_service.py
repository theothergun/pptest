# pages/dummy/dummy_controller.py
from __future__ import annotations

import queue
from typing import Optional, Any, Dict

from nicegui import ui

from layout.context import PageContext
from pages.dummy.config_models import DummyEditionState  # your edition state model (loaded from dummy_config.json)
from pages.dummy.dialogs import confirm_dialog
from pages.dummy.execution_models import ExecutionState, load_exec_progress, clear_exec_progress, DummyUIHandles
from pages.dummy.execution_dialog import create_dummy_execution_tool_window
from pages.dummy.config_models import load_config_file
from pages.dummy.scheduler import DummyScheduler
from services.ui_bridge import Subscription
from pages.dummy.historization import cleanup_history_if_needed, append_history_record


class DummyController:
	def __init__(self) -> None:
		# -----------------------------
		# GLOBAL (machine-wide) state
		# -----------------------------
		self.edition_state: Optional[DummyEditionState] = None
		self.exec_state: Optional[ExecutionState] = None

		# This controller is global in your main.py, but UI is per session.
		# So we store per-client handles/subscriptions/timers below.

		# -----------------------------
		# PER CLIENT (session) state
		# -----------------------------
		self._ctx_by_client: dict[str, Any] = {}  # PageContext per client
		self._handles_by_client: dict[str, DummyUIHandles] = {}
		self._sub_by_client: dict[str, Subscription] = {}
		self._timer_by_client: dict[str, ui.timer] = {}

		# If feature disabled by scheduler config, we skip creating anything.
		self._feature_enabled: bool = False

		# timer for periodic cleanup
		self._cleanup_timer = None
		# -----------------------------
		# MACHINE-WIDE scheduler (one instance + one timer)
		# NOTE: ui.timer is bound to a client slot, so we "attach" it to one active client.
		# If that client disconnects, we reattach on the next client start.
		# -----------------------------
		self._scheduler: Optional[DummyScheduler] = None
		self._scheduler_timer: Optional[ui.timer] = None
		self._scheduler_owner_client: Optional[str] = None

		self._history_written_for_run_key: Optional[str] = None
		self._history_lock = False

	def _current_run_key(self) -> Optional[str]:
		"""A key that uniquely identifies one completed run."""
		if not self.exec_state:
			return None
		if not self.exec_state.started_at or not self.exec_state.finished_at:
			return None

		# started_at+finished_at is usually enough; add set/dummy to be extra safe
		set_name = ""
		try:
			sel = self.exec_state.selected_set()
			set_name = sel.name if sel else ""
		except Exception:
			pass

		dummy_id = getattr(self.exec_state, "selected_dummy_id", "")
		return f"{self.exec_state.started_at}|{self.exec_state.finished_at}|{set_name}|{dummy_id}"

	def is_feature_enabled(self):
		return self._feature_enabled

	# ----- helper to start the dummy test manually
	def start_dummy_test(self, ask_for_confirmation=True):
		if ask_for_confirmation:
			confirm_dialog(title="Confirm", message="Start the Dummy test?", on_yes=self._start_dummy_test,
						   mode="warning")
		else:
			self._start_dummy_test()

	def _start_dummy_test(self):
		client_id = ui.context.client.id
		ctx = self._ctx_by_client[client_id]
		ctx.bridge.emit_patch("dummy_is_enabled", True)

	# ---------- lifecycle ----------
	def start(self, ctx) -> None:
		"""
		Called once per UI session (per browser tab / client).
		This must be per-session because NiceGUI elements are bound to the client slot.
		"""
		client_id = ui.context.client.id  # IMPORTANT: per session
		self._ctx_by_client[client_id] = ctx

		# 1) load config (edition_state) ONCE (machine-wide)
		if self.edition_state is None:
			self.edition_state = DummyEditionState()
			load_config_file(self.edition_state)

			# cleanup if needed and setup periodic cleanup check
			sched = self.edition_state.scheduler
			cleanup_history_if_needed(clean_enabled=sched.clean_enabled, older_value=sched.clean_older_value,
									  older_unit=sched.clean_older_unit)
			self._cleanup_timer = ui.timer(6 * 6 * 60,
										   lambda: cleanup_history_if_needed(clean_enabled=sched.clean_enabled,
																			 older_value=sched.clean_older_value,
																			 older_unit=sched.clean_older_unit))

			# 2) only proceed if scheduler says dummy is activated
			#    (this is the "global enable" for the feature)
			self._feature_enabled = bool(
				getattr(self.edition_state, "scheduler", None)
				and self.edition_state.scheduler.is_dummy_activated
			)

			if not self._feature_enabled:
				# feature disabled -> ensure stored progress cleared
				clear_exec_progress()
				ctx.refresh_drawer()
				return

			# 3) create execution state ONCE (machine-wide)
			self.exec_state = ExecutionState(sets=self.edition_state.sets)

			# restore progress (machine-wide) if any
			snap = load_exec_progress()
			if snap:
				self.exec_state.restore(snap)
			else:
				self.exec_state.init_defaults()

		# If feature is disabled, do nothing for this client.
		if not self._feature_enabled:
			ctx.refresh_drawer()
			return
		# 3.5) ensure machine-wide scheduler exists and is attached to a live session
		self._ensure_scheduler(client_id)

		assert self.exec_state is not None
		assert self.edition_state is not None

		# 4) Ensure tool window exists for THIS client
		self._ensure_tool_window(client_id)

		# 5) subscribe to dummy_* topics from ui_bridge (PER CLIENT queue)
		self._subscribe(client_id)

		# 6) initial apply according to ctx.state (per session)
		self._apply_initial_state(client_id)

		# set timer for msg queue (PER CLIENT)
		if client_id not in self._timer_by_client:
			self._timer_by_client[client_id] = ui.timer(
				0.1, lambda cid=client_id: self._drain_queue(cid)
			)
		ctx.refresh_drawer()

	def stop_client(self, client_id: str) -> None:
		"""Stop only this UI session — NEVER stop workers / global machine state."""
		t = self._timer_by_client.pop(client_id, None)
		if t:
			try:
				t.cancel()
			except Exception:
				pass

		sub = self._sub_by_client.pop(client_id, None)
		if sub:
			try:
				sub.close()
			except Exception:
				pass

		handles = self._handles_by_client.pop(client_id, None)
		if handles:
			try:
				handles.hide()
			except Exception:
				pass

		# If this client owns the scheduler timer, detach it (will reattach on next start)
		self._detach_scheduler_timer_if_owner(client_id)

		self._ctx_by_client.pop(client_id, None)

	# ---------- tool window creation ----------
	def _ensure_tool_window(self, client_id: str) -> None:
		"""
		Create the tool window ONCE per client.
		This must run in the page slot of that client.
		"""
		if client_id in self._handles_by_client:
			return

		ctx = self._ctx_by_client[client_id]
		assert self.exec_state is not None
		sched = self.edition_state.scheduler
		is_pred = bool(getattr(sched, "is_predetermined", False)) if sched else False

		self._handles_by_client[client_id] = create_dummy_execution_tool_window(
			ctx=ctx,
			execution_state=self.exec_state,
			is_predetermined=is_pred,
			reload_view=self._reload_view
		)

	def _reload_view(self):
		client_id = ui.context.client.id
		ctx = self._ctx_by_client[client_id]
		ctx.bridge.emit_patch("dummy_is_enabled", False)
		ui.timer(0.5, lambda: {ctx.bridge.emit_patch("dummy_is_enabled", True)}, once=True)

	# ---------- subscribe ----------
	def _subscribe(self, client_id: str) -> None:
		# Idea: subscribe to prefix "dummy_" and get (topic, value)
		if client_id not in self._sub_by_client:
			ctx = self._ctx_by_client[client_id]
			# NOTE: your bridge publishes topics like "state.dummy_*"
			self._sub_by_client[client_id] = ctx.bridge.subscribe("state.dummy_*")

	# ---------- initial apply ----------
	def _apply_initial_state(self, client_id: str) -> None:
		# If runtime says dummy window should be shown, ensure created and show.
		self._ensure_tool_window(client_id)
		ctx = self._ctx_by_client[client_id]
		uih = self._handles_by_client[client_id]

		if ctx.state.dummy_is_enabled:
			uih.show()
			uih.refresh_all()

			# spinner based on running
			uih.refresh_spinner()

		# if result already available at startup (rare), process it
		if ctx.state.dummy_result_available:
			self._on_dummy_result_available(client_id)

	# ---------- topic routing ----------
	def _on_dummy_topic(self, topic: str, value: Any) -> None:
		# NOTE: this method is left as-is, but now we route via _handle_message(client_id, ...)
		pass

	# ---------- handlers ----------
	def _on_dummy_is_enabled(self, client_id: str, enabled: bool) -> None:
		ctx = self._ctx_by_client[client_id]
		uih = self._handles_by_client.get(client_id)
		if not uih:
			self._ensure_tool_window(client_id)
			uih = self._handles_by_client[client_id]

		if enabled:
			assert self.exec_state is not None
			assert self.edition_state is not None
			# new run cycle -> allow history again
			self._history_written_for_run_key = None
			self._history_lock = False

			# sync current config (machine-wide)
			self._sync_exec_state()

			uih.show()
			uih.refresh_all()

		else:
			# hide and reset progress for a new run next time
			if self.exec_state:
				clear_exec_progress()
				self.exec_state.dummy_results = {}
				self.exec_state.started_at = None
				self.exec_state.finished_at = None

			uih.hide()

	def _on_dummy_running(self, ui_handler) -> None:
		if ui_handler:
			ui_handler.refresh_spinner()

	def _on_dummy_result_available(self, client_id: str) -> None:
		"""
		Process results once, then refresh this client's UI.
		Important: because state is machine-wide, we clear the flag to avoid
		multi-client double processing.
		"""
		if not self.exec_state or not self.edition_state:
			return

		ctx = self._ctx_by_client[client_id]
		uih = self._handles_by_client.get(client_id)

		# determine mode from scheduler settings (stored in edition_state)
		sched = getattr(self.edition_state, "scheduler", None)
		is_pred = bool(getattr(sched, "is_predetermined", False)) if sched else False
		ctx.bridge.emit_patch("dummy_test_passed", False)
		res = self.exec_state.analyse_test_result(
			ctx.state,
			is_predetermined=is_pred,
			predetermined_dummy_id=self.exec_state.selected_dummy_id,
		)

		# IMPORTANT: clear the shared flag so other sessions don't re-process
		try:
			ctx.bridge.emit_patch("dummy_test_passed", res)
			ctx.bridge.emit_patch("dummy_result_available", False)
			ctx.bridge.emit_patch("dummy_test_is_running", False)
		except Exception:
			pass

		if uih:
			uih.refresh_left()
			uih.refresh_right()

		if self.exec_state.is_finished():
			self._on_execution_finished(ctx)

	def _on_execution_finished(self, ctx: PageContext):
		# Machine-wide: ensure only one append per finished run
		run_key = self._current_run_key()
		if not run_key:
			return

		# simple re-entrancy guard (covers quick double calls in same tick)
		if self._history_lock:
			return
		self._history_lock = True
		try:
			if self._history_written_for_run_key == run_key:
				return  # already written for this run

			record = self.build_history_record_from_state()
			append_history_record(record)
			self._history_written_for_run_key = run_key

			# notify once as well
			self._scheduler.notify_execution_finished()

			ui.timer(1, lambda: (clear_exec_progress(), self.exec_state.cleanup(),
								 ctx.bridge.emit_patch("dummy_is_enabled", False)), once=True)
		finally:
			self._history_lock = False

	def _on_program_changed(self, ctx: Any | None):
		self._scheduler.notify_program_changed()
		ctx.bridge.emit_patch("dummy_program_changed", False)

	def _on_dummy_config_updated(self, client_id: str) -> None:
		"""
		Reload config (machine-wide), update derived states, and refresh UI windows.
		This is triggered by topic "dummy_config_updated".
		"""
		ctx = self._ctx_by_client.get(client_id)
		if not ctx:
			return

		# 1) reload config (machine-wide)
		if self.edition_state is None:
			self.edition_state = DummyEditionState()
		load_config_file(self.edition_state)

		# update cleanup behavior/timer using new scheduler settings
		self._restart_cleanup_timer()

		# 2) recompute feature enable (global)
		self._feature_enabled = bool(
			getattr(self.edition_state, "scheduler", None)
			and self.edition_state.scheduler.is_dummy_activated
		)

		# 3) if feature disabled now -> stop UI and clear progress (machine-wide)
		if not self._feature_enabled:
			clear_exec_progress()

			for cid, handles in list(self._handles_by_client.items()):
				try:
					handles.hide()
				except Exception:
					pass

			if self._scheduler_timer:
				try:
					self._scheduler_timer.cancel()
				except Exception:
					pass

			self._scheduler_timer = None
			self._scheduler_owner_client = None
			self._scheduler = None

			for cid, cctx in list(self._ctx_by_client.items()):
				try:
					cctx.refresh_drawer()
				except Exception:
					pass

			try:
				ctx.bridge.emit_patch("dummy_config_updated", False)
			except Exception:
				pass
			return

		# 4) feature enabled -> ensure exec_state exists
		if self.exec_state is None:
			self.exec_state = ExecutionState(sets=self.edition_state.sets)
			snap = load_exec_progress()
			if snap:
				self.exec_state.restore(snap)
			else:
				self.exec_state.init_defaults()

		# sync machine-wide config into exec_state
		self._sync_exec_state()

		# 5) ensure scheduler exists and updated
		self._ensure_scheduler(client_id)
		if self._scheduler and self.edition_state:
			self._scheduler.edition_state = self.edition_state
			self._scheduler.ctx = ctx

		# 6) refresh all live client windows (NO REBUILD)
		for cid, cctx in list(self._ctx_by_client.items()):
			uih = self._handles_by_client.get(cid)
			if not uih:
				continue

			# update execution_state inside view
			sched = self.edition_state.scheduler
			is_pred = bool(getattr(sched, "is_predetermined", False)) if sched else False
			uih.refresh_state_binding(self.exec_state, is_pred)

			# respect each client's runtime visibility
			if cctx.state.dummy_is_enabled:
				uih.show()

			try:
				cctx.refresh_drawer()
			except Exception:
				pass

		# 7) clear the flag so it doesn't retrigger
		try:
			ctx.bridge.emit_patch("dummy_config_updated", False)
		except Exception:
			pass

	def _sync_exec_state(self):
		self.exec_state.sets = self.edition_state.sets
		self.exec_state.ensure_valid_selection()
		self.exec_state.ensure_dummy_result_entries()
		self.exec_state.persist()

	def _drain_queue(self, client_id: str, max_per_tick: int = 50) -> None:
		"""Drain up to N messages per tick and dispatch updates."""
		sub = self._sub_by_client.get(client_id)
		if sub is None:
			return

		processed = 0
		try:
			while processed < max_per_tick:
				try:
					msg = sub.queue.get_nowait()
				except queue.Empty:
					break

				self._handle_message(client_id, msg.topic, msg.payload)
				processed += 1

		except RuntimeError:
			# UI slot likely gone -> stop pumping to avoid 'parent slot deleted'
			self.stop_client(client_id)

	def _handle_message(self, client_id: str, topic: str, payload: dict) -> None:
		# ctx.state already updated (per your architecture)
		ctx = self._ctx_by_client.get(client_id)
		uih = self._handles_by_client.get(client_id)

		if not ctx or not uih:
			return

		topic = topic.replace("state.", "")

		if topic == "dummy_is_enabled":
			self._on_dummy_is_enabled(client_id, bool(payload["dummy_is_enabled"]))

		elif topic == "dummy_test_is_running":
			self._on_dummy_running(uih)

		elif topic == "dummy_result_available":
			if bool(payload["dummy_result_available"]):
				# Only one session should process it; we do it here and clear the flag.
				self._on_dummy_result_available(client_id)
		elif topic == "dummy_program_changed":
			if bool(payload["dummy_program_changed"]):
				self._on_program_changed(ctx)
		elif topic == "dummy_config_updated":
			if bool(payload["dummy_config_updated"]):
				self._on_dummy_config_updated(client_id)

	# ----------- dummy historization --------------------
	def build_history_record_from_state(self) -> Dict[str, Any]:
		"""
		Requires:
		  - exec_state.started_at, exec_state.finished_at
		  - exec_state.dummy_results keyed by dummy_id with {"state": ..., "values": {inspection_id: str}}
		  - set_obj has .name and .dummies; dummy has .name and .inspections; inspection has .id and .name
		Produces dict-by-name history record.
		"""
		set_obj = self.exec_state.selected_set()
		results_by_dummy_name: Dict[str, Any] = {}
		record = {"started_at": self.exec_state.started_at, "finished_at": self.exec_state.finished_at,
				  "set_name": set_obj.name if set_obj else "", "results": results_by_dummy_name}
		if set_obj:
			for dummy in set_obj.dummies:
				entry = self.exec_state.dummy_results.get(dummy.id, {})
				state_val = entry.get("state", None)
				values_by_ins_id = entry.get("values", {}) or {}

				# map inspection id -> inspection name (unique inside dummy)
				ins_name_by_id = {ins.id: ins.name for ins in (dummy.inspections or [])}

				values_by_ins_name: Dict[str, str] = {}
				for ins_id_raw, val in values_by_ins_id.items():
					try:
						ins_id = int(ins_id_raw)
					except Exception:
						continue
					ins_name = ins_name_by_id.get(ins_id)
					if not ins_name:
						continue
					values_by_ins_name[ins_name] = str(val)

				results_by_dummy_name[dummy.name] = {
					"state": state_val,
					"values": values_by_ins_name,
				}

		return record

	# -------------- dummy scheduler ---------------------
	def _ensure_scheduler(self, client_id: str) -> None:
		"""Create scheduler once (machine-wide) and ensure a timer is attached to a live client slot."""
		if not self._feature_enabled or not self.edition_state:
			return

		# Create scheduler object once (machine-wide)
		if self._scheduler is None:
			ctx = self._ctx_by_client.get(client_id)
			if not ctx:
				return
			self._scheduler = DummyScheduler(ctx=ctx, edition_state=self.edition_state)

		# Ensure timer exists (attached to a live client)
		self._ensure_scheduler_timer(client_id)

	def _ensure_scheduler_timer(self, client_id: str) -> None:
		"""
		ui.timer belongs to the current client's slot.
		So we keep exactly one timer and bind it to one active client.
		"""
		if self._scheduler is None:
			return

		# already running
		if self._scheduler_timer is not None:
			return

		ctx = self._ctx_by_client.get(client_id)
		if not ctx:
			return

		# Keep scheduler using the newest ctx (bridge+state are global anyway, but ctx reference is used for emit_patch)
		self._scheduler.ctx = ctx
		self._scheduler_owner_client = client_id

		# tick fairly often but lightweight; adjust if needed
		self._scheduler_timer = ui.timer(0.5, lambda: self._scheduler.tick())

	def _detach_scheduler_timer_if_owner(self, client_id: str) -> None:
		if self._scheduler_owner_client != client_id:
			return
		if self._scheduler_timer:
			try:
				self._scheduler_timer.cancel()
			except Exception:
				pass
		self._scheduler_timer = None
		self._scheduler_owner_client = None

	def _restart_cleanup_timer(self) -> None:
		"""Restart periodic cleanup timer using the current scheduler settings."""
		if not self.edition_state:
			return
		sched = getattr(self.edition_state, "scheduler", None)
		if not sched:
			return

		# immediate cleanup with new settings
		cleanup_history_if_needed(
			clean_enabled=sched.clean_enabled,
			older_value=sched.clean_older_value,
			older_unit=sched.clean_older_unit,
		)

		# restart timer (timer is bound to a client slot; ok because this is called from a live client's slot)
		if self._cleanup_timer:
			try:
				self._cleanup_timer.cancel()
			except Exception:
				pass
			self._cleanup_timer = None

		self._cleanup_timer = ui.timer(
			6 * 6 * 60,
			lambda: cleanup_history_if_needed(
				clean_enabled=sched.clean_enabled,
				older_value=sched.clean_older_value,
				older_unit=sched.clean_older_unit,
			),
		)
