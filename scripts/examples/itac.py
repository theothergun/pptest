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
    if step == 0:
        username = "111111"
        password = "111111"
        station = "6410400821"
        result = ctx.worker.itac_login_user(
            "itac_mk",
            station_number=station,
            username=username,
            password=password,
            client="01",
        )
        print(result)
        if bool(result.get("ok")):
            print("login success")
        else:
            print("login failed:", result.get("error", "unknown_error"))
        ctx.goto(1)
    elif step == 1:
        res = ctx.ui.popup_message(
            "login_retry",
            "Want to retry login?",
            title="Retry login?",
            buttons=[
                {"id": "retry", "text": "Retry"},
                {"id": "cancel", "text": "Cancel"},
            ],
        )
        if res:
            if res['clicked'] == "cancel":
                ctx.goto(2)
            if res['clicked'] == "retry":
                ctx.goto(0)
    elif step == 2:
        ctx.goto(99)
        pass

# Export
main = main
