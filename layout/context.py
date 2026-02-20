from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any, Callable
from nicegui import ui

from layout.action_bar import EventBus, ActionBar
from services.app_state import AppState
from layout.observable_wrapper import ObservableWrapper
from services.ui_bridge import UiBridge
from services.worker_registry import WorkerRegistry
from services.worker_bus import WorkerBus


@dataclass
class PageContext:
	# -----------------------------
	# Layout UI references
	# -----------------------------

	# Reference to the left navigation drawer element (so header can toggle it)
	drawer: Optional[ui.left_drawer] = None
	right_drawer: Optional[ui.right_drawer] = None

	# Dynamic container inside the drawer. Only this element should be cleared and rebuilt when routes change.
	drawer_content: Optional[ui.element] = None

	# --- Callback that rebuilds the drawer_content---
	refresh_drawer: Optional[Callable[[], None]] = None

	# Label shown in the main area (often used as breadcrumb like "/home")
	breadcrumb: Optional[ui.label] = None
	device_panel_toggle_btn: Optional[ui.button] = None

	# The container where the current page content is rendered
	# (router clears it and renders the selected page inside)
	main_area: Optional[ui.column] = None

	# -----------------------------
	# Event / action bar system
	# -----------------------------

	# Per-user event bus for this page session.
	# Used for communication between components/views (e.g. ActionBar click events).
	# Usually recreated on each navigation to avoid duplicate event handlers.
	bus: Optional[EventBus] = None

	# Reference to the currently active ActionBar instance (for the active route/page).
	# Pages can use it to enable/disable/toggle actions dynamically.
	action_bar: Optional[ActionBar] = None

	# -----------------------------
	# Navigation / drawer helpers
	# -----------------------------

	# Drawer navigation buttons indexed by route key (e.g. "home", "reports").
	# Used to highlight the currently active route in the drawer.
	nav_buttons: dict[str, ui.button] = field(default_factory=dict)

	# -----------------------------
	# Errors drawer badge
	# -----------------------------

	# Badge element next to the "Errors" drawer entry (shows error count).
	# Stored so we can update the badge text/visibility from any page.
	errors_badge: Optional[ui.badge] = None

	#keep reference of icon so it can be animated when errors exist
	errors_icon_wrap: Optional[ui.element] = None

	# Optional row container holding the "Errors" button + badge.
	# Can be used if you want to hide/show the whole drawer entry.
	errors_row: Optional[ui.row] = None

	# -------- Application state (per client) --------
	# Live, UI-relevant state shared across all pages.
	# Updated by background workers via UiBridge.
	# Pages bind UI elements to this state.
	state: AppState = None

	# -------- Worker → UI communication --------
	# Thread-safe bridge used by backend workers to:
	# - patch AppState
	# - send UI notifications
	# - request UI-thread callbacks
	bridge: Optional[UiBridge] = None

	# -------- UI → Worker communication --------
	# Registry holding all backend workers for this client.
	# Pages send commands to workers via this registry.
	# Workers are started/stopped per client session.
	workers: Optional[WorkerRegistry] = None

	# -------- Worker ↔ Worker communication --------
	# In-process pub/sub bus shared by all backend workers
	# belonging to this client session.
	#
	# Workers use this bus to:
	# - publish results for other workers
	# - subscribe to topics produced by other workers
	#
	# This bus is NOT used for UI communication.
	worker_bus: Optional[WorkerBus] = None

	# -------- UI infrastructure (set elsewhere) --------
	# drawer: Optional[ui.left_drawer] = None
	# action_bar: Optional[ActionBar] = None
	# bus: Optional[EventBus] = None
	# errors_badge: Optional[ui.badge] = None


	def set_state_and_publish(self, key: str, value: Any) -> None:
		setattr(self.state, key, value)
		self.bridge.ui_publish_event(f"state.{key}", **{key: value})

	def set_state_many_and_publish(self, **values: Any) -> None:
		# 1️⃣ update UI state
		for key, value in values.items():
			self.set_state_and_publish(key, value)

		# 2️⃣ publish once (batch event)
		#self.worker_bus.publish("ui.state", **values)

