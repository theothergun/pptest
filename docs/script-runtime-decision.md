# Script Runtime Architecture Decision

## Decision

Use a central **AutomationRuntime** service (application-owned) for script orchestration, while keeping worker command/topic contracts stable.

## Why

- **Timing stability**: chain loops keep deterministic cycle behavior.
- **Isolation**: script exceptions remain per-chain, not app-wide.
- **Clear ownership**: loader, chain lifecycle, and hot-reload state are managed in one runtime service.
- **Compatibility**: existing Script Lab and worker-bus integrations continue using `ScriptWorkerCommands` and existing topics.

## Compatibility notes

- `services/script_runtime.py` exposes compatibility aliases (`ScriptRuntime = AutomationRuntime`).
- Loader still accepts legacy entry names (`step_chain`, `stepchain`) to avoid breaking old scripts.
- New docs and new scripts should use:
  - engine name: **AutomationRuntime**
  - script entry function: `main(ctx)`
