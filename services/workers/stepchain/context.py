"""Compatibility shim for legacy stepchain context imports."""

from services.automation_runtime.context import AutomationContext, PublicAutomationContext

StepChainContext = AutomationContext
PublicStepChainContext = PublicAutomationContext

__all__ = ["AutomationContext", "PublicAutomationContext", "StepChainContext", "PublicStepChainContext"]
