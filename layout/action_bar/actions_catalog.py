from typing import Union

from layout.action_bar.models import Action, ToggleAction

# You can keep route-specific action sets here
ActionButton = Union[Action, ToggleAction]
ACTIONS_BY_ROUTE: dict[str, list[ActionButton]] = {
    "vi_home": [
        ToggleAction(id="start_stop", text="Play", icon="play_arrow", default_color="positive",
            active_text = "Stop", active_icon="stop", active_color= "negative"),
        Action(id="reset_counter", text="Counter Reset", icon="restart_alt", default_color="info", enabled=True),
        Action(id="unlock", text="Unlock", icon="lock", default_color="primary", enabled=False),
        Action(id="failure_catalogue", text="Failure catalogue", icon="menu_book", default_color="warning", enabled=True),
    ],
    "errors": [
        Action(id="acknowledge", text="Acknowledge", icon="check", default_color="primary"),
        Action(id="clear_all", text="Clear All", icon="delete", default_color="primary", is_active=True),
        Action(id="add_random", text="Generate Test Error", icon="add", default_color="secondary"),
    ],
    "reports": [
        Action(id="export", text="Export", icon="download", default_color="primary"),
        Action(id="filter", text="Filter", icon="tune", default_color="secondary"),
    ],
    "settings": [
        Action(id="apply", text="Apply", icon="check", default_color="positive"),
    ],
    "home": [
        Action(id="start", text="Refresh", icon="refresh", default_color="primary"),
        Action(id="save", text="Save", icon="save", default_color="positive", enabled=False),
        Action(id="delete", text="Delete", icon="delete", default_color="negative"),
    ],
}
