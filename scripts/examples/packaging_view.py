from __future__ import annotations
from services.script_api import PublicAutomationContext, StateKeys

import time


def main(ctx: PublicAutomationContext):
	"""
	Example script for packaging using generic ctx.ui/state APIs.
	"""
	ctx.set_cycle_time(0.2)

	step = ctx.step
	if step == 0:
		# init demo values
		ctx.set_state_many(
			container_number="AB",
			part_number="@123456789",
			description="Sample part",
			current_container_qty=0,
			max_container_qty=45,
			last_serial_number="",
		)
		ctx.set_step_desc("packaging demo ready")
		ctx.goto(10)
		return

	if step == 10:
		# wait for any command from the view
		cmd = ctx.ui.consume_command("packaging.cmd")
		if cmd is None:
			ctx.set_step_desc("Waiting for packaging action...")
			return
		if cmd not in ("remove", "print", "new", "refresh"):
			return

		if cmd == "refresh":
			ctx.set_state(StateKeys.last_serial_number, time.strftime("%H:%M:%S"))
			ctx.set_step_desc("refreshed last serial time")
			return

		if cmd == "new":
			ctx.set_state_many(
				container_number="NEW-%s" % int(time.time() % 1000),
				part_number="@987654321",
				description="New part created",
				current_container_qty=0,
				max_container_qty=60,
				last_serial_number="",
			)
			ctx.set_step_desc("new container initialized")
			return

		if cmd == "print":
			ctx.notify_info("Print requested (demo)")
			ctx.set_step_desc("print requested")
			return

		if cmd == "remove":
			ctx.set_state_many(
				container_number="",
				part_number="",
				description="",
				current_container_qty=0,
				max_container_qty=0,
				last_serial_number="",
			)
			ctx.set_step_desc("values cleared")
			return


# Export
main = main
