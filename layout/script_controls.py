from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nicegui import ui

from layout.context import PageContext
from services.script_actions import (
    ScriptActionDefinition,
    get_script_metadata,
    run_script_action,
)
from services.worker_commands import ScriptWorkerCommands as ScriptCommands


@dataclass(frozen=True)
class ScriptButtonSpec:
    label: str
    icon: str = "smart_display"
    color: str = "primary"
    command: str = ScriptCommands.START_CHAIN
    script_name: str = ""
    instance_id: str = "default"
    payload: dict[str, Any] | None = None
    outline: bool = False


_COMMAND_DEFAULTS = {
    ScriptCommands.START_CHAIN: ("Start", "play_arrow", "positive"),
    ScriptCommands.STOP_CHAIN: ("Stop", "stop", "negative"),
    ScriptCommands.PAUSE_CHAIN: ("Pause", "pause", "warning"),
    ScriptCommands.RESUME_CHAIN: ("Resume", "play_arrow", "positive"),
    ScriptCommands.RETRY_CHAIN: ("Retry", "replay", "primary"),
    ScriptCommands.RELOAD_SCRIPT: ("Reload", "refresh", "info"),
}


def script_action_button(ctx: PageContext, spec: ScriptButtonSpec) -> ui.button:
    command = str(spec.command or ScriptCommands.START_CHAIN)
    default_label, default_icon, default_color = _COMMAND_DEFAULTS.get(command, ("Run", "smart_display", "primary"))
    action = ScriptActionDefinition(
        command=command,
        script_name=str(spec.script_name or ""),
        instance_id=str(spec.instance_id or "default"),
        payload=dict(spec.payload or {}),
    )
    props = f"color={spec.color or default_color}"
    if spec.outline:
        props += " outline"
    button = ui.button(
        spec.label or default_label,
        icon=spec.icon or default_icon,
        on_click=lambda: run_script_action(ctx, action),
    ).props(props)
    return button


def script_action_row(ctx: PageContext, specs: list[ScriptButtonSpec]) -> None:
    with ui.row().classes("w-full flex-wrap gap-2"):
        for spec in specs:
            script_action_button(ctx, spec)


def script_metadata_buttons(ctx: PageContext, script_name: str, *, instance_id: str = "default") -> None:
    metadata = get_script_metadata(ctx, script_name)
    buttons = list((metadata or {}).get("buttons") or [])
    if not buttons:
        ui.label("No SCRIPT_META buttons declared for this script.").classes("text-sm text-[var(--text-secondary)]")
        return

    specs: list[ScriptButtonSpec] = []
    for item in buttons:
        if not isinstance(item, dict):
            continue
        specs.append(
            ScriptButtonSpec(
                label=str(item.get("label") or item.get("id") or "Run"),
                icon=str(item.get("icon") or "smart_display"),
                color=str(item.get("color") or "primary"),
                command=str(item.get("command") or ScriptCommands.START_CHAIN),
                script_name=str(item.get("script_name") or script_name),
                instance_id=str(item.get("instance_id") or instance_id),
                payload=dict(item.get("payload") or {}),
                outline=bool(item.get("outline", False)),
            )
        )
    script_action_row(ctx, specs)
