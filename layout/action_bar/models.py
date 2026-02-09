from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Action:
    id: str
    text: str
    icon: str | None = None
    default_color: str = "primary"
    is_active: bool = False
    enabled: bool = True
    disabled_color: str = "grey-6"
    visible: bool = True # handy for "available or not"

    def get_color(self):
        return self.default_color if self.enabled else self.disabled_color

    def get_text(self):
        return self.text

    def get_icon(self):
        return self.icon


@dataclass
class ToggleAction(Action) :
    active_color: str = "primary"
    active_icon: str | None = None  # for a toggle button
    active_text: str | None = None

    def get_color(self):
        active_color = self.active_color or self.default_color
        return self.disabled_color if not self.enabled else \
            active_color if self.is_active else self.default_color
    def get_text(self):
        active_text = self.active_text or self.text
        return active_text if self.is_active else self.text

    def get_icon(self):
        active_icon = self.active_icon or self.icon
        return active_icon if self.is_active else self.icon