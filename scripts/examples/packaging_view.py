from __future__ import annotations

import time
from services.workers.stepchain.context import PublicStepChainContext


def main(ctx: PublicStepChainContext):
	"""
	Example script for the new packaging view (form with buttons).
	Uses ctx.view.packaging (alias: ctx.view.packagin).
	"""
	ctx.set_cycle_time(0.2)

	step = ctx.step
	if step == 0:
		# init demo values
		ctx.view.packaging.set_form(
			container_number="AB",
			part_number="@123456789",
			description="Sample part",
			current_qty=0,
			max_qty=45,
			last_serial_number="",
		)
		ctx.set_step_desc("packaging demo ready")
		ctx.goto(10)
		return

	if step == 10:
		# wait for any command from the view
		cmd = ctx.view.packaging.wait_cmd(
			expected=["remove", "print", "new", "refresh"],
			step_desc="Waiting for packaging action...",
		)
		if cmd is None:
			return

		if cmd == "refresh":
			ctx.view.packaging.set_last_serial_number(time.strftime("%H:%M:%S"))
			ctx.set_step_desc("refreshed last serial time")
			return

		if cmd == "new":
			ctx.view.packaging.set_form(
				container_number="NEW-%s" % int(time.time() % 1000),
				part_number="@987654321",
				description="New part created",
				current_qty=0,
				max_qty=60,
				last_serial_number="",
			)
			ctx.set_step_desc("new container initialized")
			return

		if cmd == "print":
			ctx.notify_info("Print requested (demo)")
			ctx.set_step_desc("print requested")
			return

		if cmd == "remove":
			ctx.view.packaging.set_form(
				container_number="",
				part_number="",
				description="",
				current_qty=0,
				max_qty=0,
				last_serial_number="",
			)
			ctx.set_step_desc("values cleared")
			return


# Export
main = main
