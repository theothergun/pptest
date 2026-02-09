from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING, Union

from nicegui import ui, app
from layout.action_bar.models import Action, ToggleAction
from layout.action_bar.events import EventBus
from layout.action_bar.event_types import ActionBarEvent

if TYPE_CHECKING:
    from layout.context import PageContext

ActionButton = Union[Action, ToggleAction]

class ActionBar:

    def __init__(self, ctx: "PageContext", route_key: str, actions: List[ActionButton]) -> None:
        self.ctx = ctx
        self.route_key = route_key

        if ctx.bus is None:
            ctx.bus = EventBus()
        ctx.action_bar = self
        self.bus = ctx.bus

        # base config
        self.actions: Dict[str, ActionButton] = {a.id: a for a in actions}

        # apply persisted state (per user, per route, per action)
        self._restore_persisted_state()

        self._buttons: Dict[str, ui.button] = {}

    # ---------- persistence ----------
    def _get_action_state_stored(self) -> dict:
        """
        Returns the per-user storage dictionary used to persist ActionBar state.

        Structure (stored in app.storage.user):
            action_state = {
                "<route_key>": {
                    "<action_id>": {
                        "enabled": bool,
                        "is_active": bool,
                        "visible": bool,
                    }
                }
            }
        """
        return app.storage.user.setdefault("action_state", {})

    def _get_route_action_state(self) -> dict:
        """
        Returns the state dictionary for the current route_key.

        Example return value:
            {
                "save": {"enabled": True, "is_active": False, "visible": True},
                "delete": {"enabled": False, "is_active": False, "visible": True},
            }
        """
        store = self._get_action_state_stored()
        return store.setdefault(self.route_key, {})

    def _restore_persisted_state(self) -> None:
        """
        Restore previously saved action state (enabled/active/visible) for this route.

        Note:
        - Only mutable state is restored.
        - Static config (text/icon/colors) always comes from the catalog definitions.
        """
        route_state = self._get_route_action_state()
        for action_id, saved in route_state.items():
            if action_id not in self.actions:
                continue

            a = self.actions[action_id]
            if "enabled" in saved:
                a.enabled = bool(saved["enabled"])
            if "is_active" in saved:
                a.is_active = bool(saved["is_active"])
            if "visible" in saved:
                a.visible = bool(saved["visible"])

    def _persist_action_state(self, action_id: str) -> None:
        """
        Persist the mutable state of one action (enabled/active/visible) for this route.

        This is called whenever an action changes state so that leaving the page
        and returning later restores the same button state.
        """
        a = self.actions[action_id]
        self._get_route_action_state()[action_id] = {
            "enabled": a.enabled,
            "is_active": a.is_active,
            "visible": a.visible,
        }

    # ---------- UI ----------
    def render(self, container: ui.element) -> None:
        with container:
            with ui.row().classes("w-full justify-start gap-2"):
                for action in self.actions.values():
                    if not action.visible:
                        continue
                    btn = ui.button(
                        action.text,
                        icon=action.icon,
                        on_click=lambda aid=action.id: self._handle_click(aid),
                    ).props("unelevated no-caps").classes("h-[80px]")
                    self._buttons[action.id] = btn
                    self._apply_style(action.id)

    # ---------- external API ----------
    def set_active(self, action_id: str, active: bool) -> None:
        if action_id in self.actions:
            self.actions[action_id].is_active = active
            self._persist_action_state(action_id)
            self._apply_style(action_id)

    def set_enabled(self, action_id: str, enabled: bool) -> None:
        if action_id in self.actions:
            self.actions[action_id].enabled = enabled
            self._persist_action_state(action_id)
            self._apply_style(action_id)

    def set_visible(self, action_id: str, visible: bool) -> None:
        if action_id in self.actions:
            self.actions[action_id].visible = visible
            self._persist_action_state(action_id)
            ui.notify("Visibility changed; re-render page to reflect it.")

    def update(self, action_id, *, enabled: bool = True, active: bool = False, visible:bool = True):
        if action_id in self.actions:
            self.actions[action_id].visible = visible
            self.actions[action_id].enabled = enabled
            self.actions[action_id].is_active = active
            self._persist_action_state(action_id)
            self._apply_style(action_id)

    # ---------- internal ----------
    def _handle_click(self, action_id: str) -> None:
        action = self.actions.get(action_id)
        if not action or not action.enabled:
            return
        self.bus.emit(ActionBarEvent.CLICKED, action_id, action)

    def _apply_style(self, action_id: str) -> None:
        action = self.actions[action_id]
        btn = self._buttons.get(action_id)
        if not btn:
            return
        color = action.get_color()
        icon = action.get_icon()
        btn.props(f"color={color} icon={icon}")
        btn.set_enabled(action.enabled)
        btn.set_text(action.get_text())
