from __future__ import annotations

import tempfile
import time
from pathlib import Path

from services.script_runtime import ScriptRuntime
from services.ui_bridge import UiBridge
from services.worker_bus import WorkerBus
from services.worker_commands import ScriptWorkerCommands as Commands


def _wait_until(predicate, timeout_s: float = 2.0) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scripts_dir = Path(tmp)
        script_path = scripts_dir / "demo.py"
        script_path.write_text(
            "def chain(ctx):\n"
            "    val = ctx.values.by_key('regression.input', 0)\n"
            "    ctx.vars.set('output', f'v1:{val}')\n",
            encoding="utf-8",
        )

        bridge = UiBridge()
        bus = WorkerBus()
        sub = bus.subscribe("VALUE_CHANGED")
        runtime = ScriptRuntime(
            name="script_worker",
            bridge=bridge,
            worker_bus=bus,
            send_cmd=lambda worker, cmd, payload: None,
            scripts_dir=scripts_dir,
            reload_check_interval=0.2,
        )

        runtime.start()
        runtime.send(Commands.START_CHAIN, script_name="demo", instance_id="default")

        bus.publish("VALUE_CHANGED", source="test", source_id="publisher", key="regression.input", value=7)

        def has_v1() -> bool:
            while True:
                try:
                    msg = sub.queue.get_nowait()
                except Exception:
                    break
                payload = msg.payload
                if payload.get("key") == Commands.UPDATE_CHAIN_STATE:
                    state = payload.get("value") or {}
                    if str(state.get("chain_key", "")).startswith("demo:"):
                        if (state.get("data") or {}).get("output") == "v1:7":
                            return True
            return False

        assert _wait_until(has_v1), "expected v1 output"

        script_path.write_text(
            "def chain(ctx):\n"
            "    val = ctx.values.by_key('regression.input', 0)\n"
            "    ctx.vars.set('output', f'v2:{val}')\n",
            encoding="utf-8",
        )
        runtime.send(Commands.RELOAD_SCRIPT, script_name="demo")
        bus.publish("VALUE_CHANGED", source="test", source_id="publisher", key="regression.input", value=9)

        def has_v2() -> bool:
            while True:
                try:
                    msg = sub.queue.get_nowait()
                except Exception:
                    break
                payload = msg.payload
                if payload.get("key") == Commands.UPDATE_CHAIN_STATE:
                    state = payload.get("value") or {}
                    if (state.get("data") or {}).get("output") == "v2:9":
                        return True
            return False

        assert _wait_until(has_v2), "expected v2 output after reload"

        bad_path = scripts_dir / "bad.py"
        bad_path.write_text("def chain(ctx):\n    raise RuntimeError('boom')\n", encoding="utf-8")
        runtime.send(Commands.START_CHAIN, script_name="bad", instance_id="default")

        assert _wait_until(lambda: runtime.is_alive()), "runtime should remain alive after bad script exception"

        runtime.stop()
        sub.close()


if __name__ == "__main__":
    main()
