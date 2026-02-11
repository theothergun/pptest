import time
from enum import StrEnum

from services.workers.stepchain.context import PublicStepChainContext

class UI(StrEnum) :


	PART_GOOD = "part_good"

	SCANNER_1 = "scanner_1"

def main(ctx: PublicStepChainContext):
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
		part_good = ctx.get_state( "part_good", 0)
		ctx.set_state("part_good" ,  part_good +1  )
		ctx.set_state("work_instruction",  ctx.read_tcp("scanner1"))
		counter = ctx.vars.get("counter", 0) or 0
		counter = int(counter) + 1
		ctx.vars.set("counter", counter)
		ctx.set_step_desc( "count=%s" % counter)
		time.sleep(0.03)
		if counter >= 5:
			ctx.goto(30)
		else:
			ctx.goto(20)

	elif step == 20:
		# Short wait and back to count
		ctx.set_step_desc("waiting briefly")
		#time.sleep(0.05)
		ctx.goto(10)

	elif step == 30:
		# Notify / finish / reset
		ctx.set_step_desc("demo chain finished (counter reached 5)")
		time.sleep(0.05)
		ctx.goto(0)

	else:
		# Unknown step: reset safely
		ctx.set_step_desc("unknown step=%s; reset" % step)
		ctx.goto(0)


# Export (your loader may look for main/chain/<basename>)
main = main
