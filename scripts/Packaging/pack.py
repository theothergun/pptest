import time
from enum import StrEnum

from services.workers.stepchain.context import PublicStepChainContext

class UI(StrEnum) :
	PART_GOOD = "part_good"
	PART_BAD = "part_bad"
	SCANNER_1 = "scanner_1"

	INSTRUCTION = "work_instruction"
	FEEDBACK = "work_feedback"

	INSTRUCTION_STATE = "work_instruction_state"
	FEEDBACK_STATE =  "work_feedback_state"

	ERRORS = "error_count"


	CONTAINER = "container_number"
	PART_NUMBER = "part_number"
	DESCRIPTION = "description"
	CURRENT_QTY =  "current_container_qty"
	MAX_QUANTITY = "max_container_qty"



def main(ctx: PublicStepChainContext):
	"""
	Simple demo chain.

	Notes:
	- Keep ctx.vars values JSON-safe (no objects, no ctx, no bus, no bridge).
	- Avoid long blocking sleeps; keep them short since the worker is single-threaded per chain tick.
	"""
	# cycle_time controls how often the worker calls this function again (seconds)
	ctx.set_cycle_time(1)
	step = ctx.step
	print("current step %s" % step)
	rid = ""
	if step == 0:
		# Initialize counters / state
		ctx.vars.set("counter", 0)
		ctx.set_step_desc("idle -> count")
		ctx.goto(10)
	elif step == 10:
		ctx.set_state(UI.INSTRUCTION , "Please scan a part")
		ctx.set_state(UI.FEEDBACK, "Waiting for rail in...")
		ctx.set_state(UI.INSTRUCTION_STATE , 4)
		ctx.set_state(UI.FEEDBACK_STATE, 2)
		#= 888
		#res = ctx.itac_station_setting("itac_main", ["WORKORDER_NUMBER"])
		#print(res)
		part_good = ctx.get_state( UI.PART_GOOD, 0)
		ctx.set_state(UI.PART_GOOD ,  part_good +1  )
		ctx.goto(20)
		time.sleep(1)
	elif step == 20:
		ctx.set_state(UI.FEEDBACK, "Requesting feedback from mes...")
		ctx.set_state(UI.INSTRUCTION_STATE , 4)
		ctx.set_state(UI.FEEDBACK_STATE, 2)
		ctx.goto(30)
		res = ctx.itac_custom_function("itac_main", "NOXPackaging.getPackInfo",in_args=["6302028220" , True])
		print(res)
		if res["result"]["return_value"] == 0:
			res_vals = res["result"]["outArgs"]
			ctx.set_state(UI.CONTAINER,res_vals[0])
			ctx.set_state(UI.PART_NUMBER,res_vals[1])
			ctx.set_state(UI.DESCRIPTION, res_vals[2])
			print(int(res_vals[3].replace(".0","")))
			print(int(res_vals[4].replace(".0", "")))
			ctx.set_state(UI.CURRENT_QTY, int(res_vals[3].replace(".0","")))
			#ctx.set_state(UI.CURRENT_QTY, 79)
			ctx.set_state(UI.MAX_QUANTITY,  int(res_vals[4].replace(".0","")))


	elif step == 30:
		ctx.set_state(UI.FEEDBACK, "Mes ok ")
		ctx.set_state(UI.INSTRUCTION_STATE , 1)
		ctx.set_state(UI.FEEDBACK_STATE, 1)
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
