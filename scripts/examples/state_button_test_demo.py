from __future__ import annotations

import time

from services.script_api import PublicAutomationContext, StateKeys, ViewButtons, ViewName


def main(ctx: PublicAutomationContext):
    """
    Demo script for state/button test page.

    Start this chain from Scripts Lab and open the test view.
    It periodically toggles:
    - AppState values
    - button enabled
    - button visibility
    """
    ctx.set_cycle_time(0.2)

    if ctx.step == 0:
        ctx.set_data("demo_phase", False)
        ctx.set_state(StateKeys.container_number, "DEMO-000")
        ctx.set_state(StateKeys.part_number, "3617836139")
        ctx.set_state(StateKeys.description, "State/button test demo")
        ctx.set_state(StateKeys.current_container_qty, 0)
        ctx.set_state(StateKeys.max_container_qty, 20)
        ctx.set_state(StateKeys.work_instruction, "Demo initialized")
        ctx.set_state(StateKeys.work_feedback, "Waiting for next toggle")
        ctx.goto(10)
        return

    if ctx.step == 10:
        if not ctx.timing.timeout(2.0):
            return
        ctx.goto(20)
        return

    if ctx.step == 20:
        phase = not bool(ctx.get_data("demo_phase", False))
        ctx.set_data("demo_phase", phase)

        now_label = time.strftime("%H:%M:%S")
        qty = int(ctx.get_state(StateKeys.current_container_qty, 0) or 0)
        qty = (qty + 1) % 21
        ctx.set_state(StateKeys.current_container_qty, qty)
        ctx.set_state(StateKeys.last_serial_number, f"DEMO-{now_label}")
        ctx.set_state(StateKeys.work_instruction, f"phase={phase} at {now_label}")
        ctx.set_state(StateKeys.work_feedback, "Buttons toggle every 2 seconds")

        # container_management
        ctx.ui.set_button_enabled(
            ViewButtons.REMOVE_SERIAL,
            phase,
            view_id=ViewName.CONTAINER_MANAGEMENT,
        )
        ctx.ui.set_button_visible(
            ViewButtons.REMOVE_ALL,
            phase,
            view_id=ViewName.CONTAINER_MANAGEMENT,
        )

        # packaging
        ctx.ui.set_button_enabled(
            ViewButtons.REFRESH,
            phase,
            view_id=ViewName.PACKAGING,
        )
        ctx.ui.set_button_visible(
            ViewButtons.PRINT,
            phase,
            view_id=ViewName.PACKAGING,
        )

        # packaging_nox
        ctx.ui.set_button_enabled(
            ViewButtons.START,
            phase,
            view_id=ViewName.PACKAGING_NOX,
        )
        ctx.ui.set_button_visible(
            ViewButtons.STOP,
            phase,
            view_id=ViewName.PACKAGING_NOX,
        )

        ctx.goto(10)


main = main

