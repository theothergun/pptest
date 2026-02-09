from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:
    from enum import Enum
    class StrEnum(str, Enum): ...

class ActionBarEvent(StrEnum):
    CLICKED = "action_bar_clicked"