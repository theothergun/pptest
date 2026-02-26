from __future__ import annotations
from services.script_api import PublicAutomationContext

import time


def main(ctx: PublicAutomationContext):
    """
    Example script using generic automation APIs.
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
