from __future__ import annotations

from services.script_api import PublicAutomationContext


SCRIPT_META = {
    "title": "Page Designer Demo",
    "description": "Simple demo script used by the Page Designer route and the developer docs.",
    "buttons": [
        {
            "id": "start_demo",
            "label": "Start Demo",
            "icon": "play_arrow",
            "color": "positive",
            "command": "script.start_chain",
        },
        {
            "id": "pause_demo",
            "label": "Pause Demo",
            "icon": "pause",
            "color": "warning",
            "command": "script.pause_chain",
        },
        {
            "id": "resume_demo",
            "label": "Resume Demo",
            "icon": "play_arrow",
            "color": "primary",
            "command": "script.resume_chain",
            "outline": True,
        },
        {
            "id": "stop_demo",
            "label": "Stop Demo",
            "icon": "stop",
            "color": "negative",
            "command": "script.stop_chain",
        },
    ],
}


def main(ctx: PublicAutomationContext) -> None:
    ctx.publish_changes(True)
    current_step = ctx.step

    if current_step == 0:
        ctx.set_step_desc("Initializing demo")
        ctx.set_state_many(designer_demo_status="Running", designer_demo_cycle=ctx.cycle_count)
        ctx.goto(10, "Demo active")
        return

    if current_step == 10:
        ctx.set_step_desc("Demo active")
        ctx.set_state_many(designer_demo_status="Active", designer_demo_cycle=ctx.cycle_count)
        if ctx.wait(1.0, 20, "Finishing cycle"):
            return
        return

    if current_step == 20:
        ctx.set_step_desc("Finishing cycle")
        ctx.set_state_many(designer_demo_status="Done", designer_demo_cycle=ctx.cycle_count)
        ctx.goto(10, "Demo active")
