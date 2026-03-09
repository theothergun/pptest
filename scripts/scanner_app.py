from __future__ import annotations
from services.script_api import PublicAutomationContext


from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

def main(ctx: PublicAutomationContext):
    ctx.log_debug(f"scanner_app step={ctx.step}")
    if ctx.step == 0:
        if ctx.wait(2, next_step=10, desc="Step 2"):
            ctx.log_info("scanner_app transitioned to step 10")
            return  # important: end tick after scheduling jump
    elif ctx.step == 10:
        # do step 10 work
        ctx.set_step_desc("scanner_app idle")
