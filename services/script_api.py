from __future__ import annotations

"""
One-stop imports for automation scripts.

Example:
    from services.script_api import (
        PublicAutomationContext,
        t,
        UiActionName,
        ViewName,
        ViewButtons,
        StateKeys,
    )
"""

from services.automation_runtime.context import PublicAutomationContext
from services.i18n import t
from services.ui.registry import (
    UiActionName,
    ViewName,
    ViewButtons,
    StateKeys,
    view_wait_key,
)

__all__ = [
    "PublicAutomationContext",
    "t",
    "UiActionName",
    "ViewName",
    "ViewButtons",
    "StateKeys",
    "view_wait_key",
]
