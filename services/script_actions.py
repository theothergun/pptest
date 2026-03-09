from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from nicegui import ui

from layout.context import PageContext
from services.worker_commands import ScriptWorkerCommands as ScriptCommands


@dataclass(frozen=True)
class ScriptActionDefinition:
    command: str
    script_name: str
    instance_id: str = "default"
    payload: dict[str, Any] | None = None


def _runtime_from(ctx_or_runtime: PageContext | Any):
    return getattr(ctx_or_runtime, "script_runtime", None) or ctx_or_runtime


def _send(runtime: Any, command: str, **payload: Any) -> bool:
    if runtime is None:
        ui.notify("Script runtime not available", type="negative")
        return False
    runtime.send(command, **payload)
    return True


def start_script(ctx_or_runtime: PageContext | Any, script_name: str, *, instance_id: str = "default", **payload: Any) -> bool:
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.START_CHAIN, script_name=script_name, instance_id=instance_id, **payload)


def stop_script(ctx_or_runtime: PageContext | Any, *, chain_key: str | None = None, script_name: str | None = None, instance_id: str = "default") -> bool:
    payload = {"chain_key": chain_key} if chain_key else {"script_name": script_name, "instance_id": instance_id}
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.STOP_CHAIN, **payload)


def pause_script(ctx_or_runtime: PageContext | Any, *, chain_key: str | None = None, script_name: str | None = None, instance_id: str = "default") -> bool:
    payload = {"chain_key": chain_key} if chain_key else {"script_name": script_name, "instance_id": instance_id}
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.PAUSE_CHAIN, **payload)


def resume_script(ctx_or_runtime: PageContext | Any, *, chain_key: str | None = None, script_name: str | None = None, instance_id: str = "default") -> bool:
    payload = {"chain_key": chain_key} if chain_key else {"script_name": script_name, "instance_id": instance_id}
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.RESUME_CHAIN, **payload)


def retry_script(ctx_or_runtime: PageContext | Any, *, chain_key: str | None = None, script_name: str | None = None, instance_id: str = "default") -> bool:
    payload = {"chain_key": chain_key} if chain_key else {"script_name": script_name, "instance_id": instance_id}
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.RETRY_CHAIN, **payload)


def reload_script(ctx_or_runtime: PageContext | Any, script_name: str) -> bool:
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.RELOAD_SCRIPT, script_name=script_name)


def reload_all_scripts(ctx_or_runtime: PageContext | Any) -> bool:
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.RELOAD_ALL)


def list_scripts(ctx_or_runtime: PageContext | Any) -> bool:
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.LIST_SCRIPTS)


def list_chains(ctx_or_runtime: PageContext | Any) -> bool:
    return _send(_runtime_from(ctx_or_runtime), ScriptCommands.LIST_CHAINS)


def get_script_metadata(ctx_or_runtime: PageContext | Any, script_name: str) -> dict[str, Any]:
    runtime = _runtime_from(ctx_or_runtime)
    loader = getattr(runtime, "loader", None)
    if loader is None:
        return {}
    return loader.get_script_metadata(script_name) or {}


def list_script_metadata(ctx_or_runtime: PageContext | Any, script_names: Iterable[str] | None = None) -> list[dict[str, Any]]:
    runtime = _runtime_from(ctx_or_runtime)
    loader = getattr(runtime, "loader", None)
    if loader is None:
        return []
    names = list(script_names or loader.list_available_scripts())
    return [loader.get_script_metadata(name) or {"name": name} for name in names]


def run_script_action(ctx_or_runtime: PageContext | Any, action: ScriptActionDefinition) -> bool:
    payload = dict(action.payload or {})
    payload.setdefault("script_name", action.script_name)
    payload.setdefault("instance_id", action.instance_id)
    return _send(_runtime_from(ctx_or_runtime), action.command, **payload)
