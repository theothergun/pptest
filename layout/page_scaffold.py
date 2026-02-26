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
    content_padding_classes: str = "",
    scroll_mode: ScrollMode = "scaffold",
) -> None:
    def has_action_bar() -> bool:
        return ctx.action_bar is not None

    with container:
        with ui.column().classes("w-full h-full min-h-0 min-w-0 app-shell p-3"):
            if title:
                ui.label(title).classes("text-2xl font-bold text-[var(--text-primary)]")

            scroll_class = "overflow-auto" if scroll_mode == "scaffold" else "overflow-hidden"
            with ui.column().classes(
                f"w-full flex-1 min-h-0 min-w-0 {scroll_class} {content_padding_classes or ''}"
            ) as content_area:
                content(content_area)

            if show_action_bar and has_action_bar():
                with ui.column().classes("w-full shrink-0 app-panel p-2"):
                    if actions_title:
                        ui.label(actions_title).classes("text-sm text-[var(--text-secondary)]")
                    ctx.action_bar.render(ui.column().classes("w-full"))

                if on_action_clicked is not None:
                    if ctx.bus is None:
                        raise RuntimeError("ctx.bus is None: router must create EventBus before rendering pages")
                    ctx.bus.on(ActionBarEvent.CLICKED, on_action_clicked)
