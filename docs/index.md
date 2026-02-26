# MES App Documentation Index

This documentation reflects the current codebase in this repository (NiceGUI app + `AutomationRuntime` scripting engine).

## Start here

1. [Quick Start](quick_start.md)
2. [View and Script Basics](scripting/view-and-script-basics.md)
3. [Scripting Engine — Practical Guide](scripting/practical_guide.md)

## Reference pages

- [Automation Runtime Programmer's Manual](stepchain_programmers_manual.md)
- [View Action Standard](view_action_standard.md)
- [Script Runtime Architecture Decision](script-runtime-decision.md)

## What changed in naming

Older docs and comments may still mention **StepChain**. In the current code this is named:

- Runtime service: `AutomationRuntime` (`services/automation_runtime/runtime.py`)
- Script context: `PublicAutomationContext` (`services/automation_runtime/context.py`)
- Script helper import: `from services.script_api import PublicAutomationContext`

Compatibility aliases still exist (`ScriptRuntime`, `step_chain`, `stepchain` entry names), but new documentation uses **Automation Runtime** consistently.
