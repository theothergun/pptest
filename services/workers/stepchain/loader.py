"""Compatibility shim for legacy stepchain loader imports."""

from services.automation_runtime.loader import AutomationScriptLoader

ScriptLoader = AutomationScriptLoader

__all__ = ["AutomationScriptLoader", "ScriptLoader"]
