from __future__ import annotations

from typing import Callable, Optional, Literal
from nicegui import ui

from layout.action_bar import Action, ActionBarEvent
from layout.context import PageContext


ContentBuilder = Callable[[ui.element], None]
ActionHandler = Callable[[str, Action], None]
ScrollMode = Literal["scaffold", "none"]


def build_page(
	ctx: PageContext,
	container: ui.element,
	*,
	title: str | None = None,
	content: ContentBuilder,
	show_action_bar: bool = True,
	actions_title: str | None = None,
	on_action_clicked: Optional[ActionHandler] = None,
	content_padding_classes: str = "",  # e.g. "pr-1"
	scroll_mode: ScrollMode = "scaffold",
) -> None:
	"""
	Standard page layout:

	- Fills available height (h-full + min-h-0)
	- Optional pinned action bar at bottom
	- Scroll behavior selectable:
		- scroll_mode="scaffold": the scaffold content area scrolls (default, current behavior)
		- scroll_mode="none": scaffold does NOT scroll; page content must manage its own scroll
	"""

	def has_action_bar() -> bool:
		return ctx.action_bar is not None

	with container:
		# Outer column must be full height and allow inner flex child to shrink
		with ui.column().classes("w-full h-full min-h-0 min-w-0"):
			if title:
				ui.label(title).classes("text-2xl font-bold")

			if scroll_mode == "scaffold":
				# Scrollable content area (ONLY this part scrolls)
				with ui.column().classes(
					"w-full flex-1 min-h-0 min-w-0 overflow-auto %s" % (content_padding_classes or "")
				) as content_area:
					content(content_area)
			else:
				# No scaffold scrolling. Page must manage scroll inside `content_area`.
				with ui.column().classes(
					"w-full flex-1 min-h-0 min-w-0 overflow-hidden %s" % (content_padding_classes or "")
				) as content_area:
					content(content_area)

			# Pinned bottom action bar (optional)
			if show_action_bar and has_action_bar():
				with ui.column().classes("w-full shrink-0"):
					ui.separator().classes("my-1")
					if actions_title:
						ui.label(actions_title).classes("text-sm text-gray-500")
					ctx.action_bar.render(ui.column().classes("w-full mb-1"))

				if on_action_clicked is not None:
					if ctx.bus is None:
						raise RuntimeError("ctx.bus is None: router must create EventBus before rendering pages")
					ctx.bus.on(ActionBarEvent.CLICKED, on_action_clicked)
