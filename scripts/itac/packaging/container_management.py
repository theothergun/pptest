from __future__ import annotations

import time

from services.workers.stepchain.context import PublicStepChainContext


def main(ctx: PublicStepChainContext):
    ctx.set_cycle_time(0.2)

    step = ctx.step
    if step == 0:
        pass

    if step != 10:
        ctx.goto(10)
        return

    payload = ctx.view.container_management.consume_payload()


    cmd = None
    if cmd in ("search_container", "search"):

        return

    if cmd == "search_serial":

        return

    if cmd == "activate":

        return

    if cmd == "refresh":

        return

    if cmd == "remove_serial":

        return

    if cmd == "remove_all":

        return

    ctx.set_step_desc("ignored command: %s" % cmd)


# Export
main = main
