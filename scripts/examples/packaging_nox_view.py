from __future__ import annotations

import time
from services.automation_runtime.context import PublicAutomationContext


def main(ctx: PublicAutomationContext):
	"""
	Example script for the old packaging view (packaging_nox).
	Buttons send commands: start/stop/reset on packaging.cmd.
	"""
	ctx.set_cycle_time(0.2)

	step = ctx.step
	if step == 0:
		ctx.view.packaging_nox.set_container_number("SP08000001AB")
		ctx.view.packaging_nox.set_part_number("3617836139")
		ctx.view.packaging_nox.set_description("Demo part")
		ctx.view.packaging_nox.set_current_qty(0)
		ctx.view.packaging_nox.set_max_qty(45)
		ctx.view.packaging_nox.set_totals(good=0, bad=0)
		ctx.view.packaging_nox.show_instruction(
			instruction="Press Start to begin",
			feedback="Idle",
			instruction_state="info",
			feedback_state="idle",
		)
		ctx.vars.set("running", False)
		ctx.vars.set("last_tick", time.time())
		ctx.goto(10)
		return

	if step == 10:
		cmd = ctx.view.packaging_nox.consume_cmd()
		if cmd == "start":
			ctx.vars.set("running", True)
			ctx.view.packaging_nox.show_instruction(
				instruction="Packing in progress",
				feedback="Running",
				instruction_state="ok",
				feedback_state="ok",
			)
		elif cmd == "stop":
			ctx.vars.set("running", False)
			ctx.view.packaging_nox.show_instruction(
				instruction="Stopped by operator",
				feedback="Stopped",
				instruction_state="warn",
				feedback_state="warn",
			)
		elif cmd == "reset":
			ctx.vars.set("running", False)
			ctx.view.packaging_nox.set_current_qty(0)
			ctx.view.packaging_nox.set_totals(good=0, bad=0)
			ctx.view.packaging_nox.show_instruction(
				instruction="Reset done",
				feedback="Idle",
				instruction_state="info",
				feedback_state="idle",
			)

		# demo counter update when running
		if ctx.vars.get("running", False):
			now = time.time()
			last = ctx.vars.get("last_tick", now)
			if now - last >= 1.0:
				ctx.vars.set("last_tick", now)
				cur = int(ctx.view.packaging_nox.get_state("current_container_qty", 0) or 0) + 1
				ctx.view.packaging_nox.set_current_qty(cur)
				ctx.view.packaging_nox.set_totals(good=cur, bad=0)


# Export
main = main
