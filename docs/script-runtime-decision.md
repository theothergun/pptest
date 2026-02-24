# Script Runtime Architecture Decision

## Decision
Refactor `ScriptWorker` responsibilities into a central `ScriptRuntime` service owned by app core.

## Why (criteria)
- **Threading/timing**: script chains already run per-chain threads with ~100ms cycle semantics; keeping chain threads while moving orchestration out of worker registry preserves timing.
- **Isolation**: script exceptions are isolated per chain and pause only the failing chain; central runtime preserves this while decoupling from worker lifecycle crashes.
- **Backpressure/latency**: central runtime keeps bus draining and command handling independent from chain tick execution, reducing risk that worker-thread bookkeeping delays event routing.
- **State ownership**: script registry, chain lifecycle, and hot-reload state are now clearly owned by one app-level service (`ScriptRuntime`) instead of being split across worker infrastructure.
- **Hot reload correctness**: runtime still requests and mirrors UI state and processes reload commands, but ownership is explicit and easier to coordinate with UI/app-level actions.
- **Maintainability**: treating scripts as a core engine clarifies architecture (runtime service + worker ecosystem), while preserving existing command/topic contracts so UI code remains stable.

## Compatibility approach
- Keep existing `ScriptWorkerCommands` and bus payloads unchanged.
- Expose a `send(...)`/`is_alive()` handle on `ScriptRuntime`, so existing call sites that only send commands continue to work with minimal updates.
- Keep other workers unchanged.
