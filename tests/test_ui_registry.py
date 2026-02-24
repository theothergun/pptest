from __future__ import annotations

import unittest

import sys
import types

if "nicegui" not in sys.modules:
    sys.modules["nicegui"] = types.SimpleNamespace(ui=types.SimpleNamespace())
if "loguru" not in sys.modules:
    sys.modules["loguru"] = types.SimpleNamespace(logger=types.SimpleNamespace(warning=lambda *a, **k: None))

from services.ui.registry import (
    from_view_command,
    UiActionName,
    UiEvent,
    ViewName,
    ViewRegistryError,
    VIEW_ACTIONS,
    VIEW_EVENTS,
    list_registry,
    parse_view_action,
)


class UiRegistryTests(unittest.TestCase):
    def test_parse_valid_command(self) -> None:
        payload = {
            "action": {
                "view": ViewName.CONTAINER_MANAGEMENT.value,
                "name": UiActionName.ACTIVATE.value,
                "event": UiEvent.CLICK.value,
            },
            "event_id": 1771943199560150100,
            "wait_modal_key": "view.wait.container_management",
            "source_id": "ui",
        }
        class _A:
            view = payload["action"]["view"]
            name = payload["action"]["name"]
            event = payload["action"]["event"]

        class _C:
            action = _A()

        ref = from_view_command(_C())
        self.assertEqual(ref.view.value, ViewName.CONTAINER_MANAGEMENT.value)
        self.assertEqual(ref.name.value, UiActionName.ACTIVATE.value)
        self.assertEqual(ref.event.value, UiEvent.CLICK.value)

    def test_unknown_view_action_event_raise(self) -> None:
        with self.assertRaises(ViewRegistryError):
            parse_view_action(view="unknown_view", name=UiActionName.ACTIVATE.value, event=UiEvent.CLICK.value)
        with self.assertRaises(ViewRegistryError):
            parse_view_action(view=ViewName.PACKAGING.value, name="unknown_action", event=UiEvent.CLICK.value)
        with self.assertRaises(ViewRegistryError):
            parse_view_action(view=ViewName.PACKAGING.value, name=UiActionName.REFRESH.value, event="unknown_event")

    def test_registry_uniqueness_and_discovery(self) -> None:
        views = [v.value for v in ViewName]
        actions = [a.value for a in UiActionName]
        events = [e.value for e in UiEvent]
        self.assertEqual(len(views), len(set(views)))
        self.assertEqual(len(actions), len(set(actions)))
        self.assertEqual(len(events), len(set(events)))

        for view, allowed_actions in VIEW_ACTIONS.items():
            self.assertEqual(len(allowed_actions), len(set(allowed_actions)))
            self.assertTrue(view in VIEW_EVENTS)

        snap = list_registry()
        self.assertIn(ViewName.PACKAGING.value, snap["views"])
        self.assertIn(UiActionName.RESET.value, snap["actions"][ViewName.PACKAGING.value])


if __name__ == "__main__":
    unittest.main()
