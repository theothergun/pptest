from __future__ import annotations
from services.script_api import PublicAutomationContext, StateKeys

import time


def main(ctx: PublicAutomationContext):
	"""
	Example script for packaging_nox using generic ctx.ui/state APIs.
	"""
	ctx.set_cycle_time(0.2)

	step = ctx.step
	if step == 0:
		ctx.set_state_many(
			container_number="SP08000001AB",
			part_number="3617836139",
			description="Demo part",
			current_container_qty=0,
			max_container_qty=45,
			part_good=0,
			part_bad=0,
		)
		ctx.ui.show(
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
		cmd = ctx.ui.consume_command("packaging.cmd")
		if cmd == "start":
			ctx.vars.set("running", True)
			ctx.ui.show(
				instruction="Packing in progress",
				feedback="Running",
				instruction_state="ok",
				feedback_state="ok",
			)
		elif cmd == "stop":
			ctx.vars.set("running", False)
			ctx.ui.show(
				instruction="Stopped by operator",
				feedback="Stopped",
				instruction_state="warn",
				feedback_state="warn",
			)
		elif cmd == "reset":
			ctx.vars.set("running", False)
			ctx.set_state_many(current_container_qty=0, part_good=0, part_bad=0)
			ctx.ui.show(
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
				cur = int(ctx.get_state(StateKeys.current_container_qty, 0) or 0) + 1
				ctx.set_state_many(current_container_qty=cur, part_good=cur, part_bad=0)


# Export
main = main
