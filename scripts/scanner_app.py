from __future__ import annotations

import time
from services.automation_runtime.context import PublicAutomationContext


def main(ctx: PublicAutomationContext):
    """
    Example script for the new packaging view (form with buttons).
    Uses ctx.view.packaging (alias: ctx.view.packagin).
    """
    ctx.set_cycle_time(1)

    step = ctx.step
    print(step)
    if step == 0:
        pass
    elif step == 1:
        pass
    elif step == 2:
        pass

# Export
main = main
