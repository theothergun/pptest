from services.script_api import PublicAutomationContext, StateKeys
from enum import StrEnum


from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

class UI(StrEnum) :


	PART_GOOD = "part_good"

	SCANNER_1 = "scanner_1"

def main(ctx: PublicAutomationContext):
	"""
	Simple demo chain.

	Notes:
	- Keep ctx.vars values JSON-safe (no objects, no ctx, no bus, no bridge).
	- Avoid long blocking sleeps; keep them short since the worker is single-threaded per chain tick.
	"""
	# cycle_time controls how often the worker calls this function again (seconds)
	ctx.set_cycle_time(0.5)
	step = ctx.step
	if step == 0:
		# Initialize counters / state


		ctx.vars.set("counter", 0)
		ctx.set_step_desc("idle -> count")
		ctx.goto(10)
	elif step == 10:
		#= 888
		#ctx.send_tcp()
		part_good = ctx.get_state( StateKeys.part_good, 0)
		ctx.set_state(StateKeys.part_good ,  part_good +1  )
		ctx.set_state(StateKeys.work_instruction,  ctx.read_tcp("scanner1"))
		counter = ctx.vars.get("counter", 0) or 0
		counter = int(counter) + 1
		ctx.vars.set("counter", counter)
		ctx.set_step_desc( "count=%s" % counter)
		if counter >= 5:
			ctx.goto(30)
		else:
			ctx.goto(20)

	elif step == 20:
		# Short wait and back to count
		ctx.set_step_desc("waiting briefly")
		if ctx.wait(0.05, 10, "waiting briefly"):
			return

	elif step == 30:
		# Notify / finish / reset
		ctx.set_step_desc("demo chain finished (counter reached 5)")
		if ctx.wait(0.05, 0, "reset"):
			return

	else:
		# Unknown step: reset safely
		ctx.set_step_desc("unknown step=%s; reset" % step)
		ctx.goto(0)

