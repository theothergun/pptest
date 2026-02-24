"""Compatibility shim for legacy imports."""

from services.automation_runtime.runtime import AutomationRuntime

ScriptRuntime = AutomationRuntime

__all__ = ["AutomationRuntime", "ScriptRuntime"]
