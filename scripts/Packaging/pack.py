from enum import StrEnum

from services.automation_runtime.context import PublicAutomationContext
from services.automation_runtime.apis.api_utils import to_int


# ------------------------------------------------------------------ UI keys (AppState)

class UI_VAR(StrEnum):
	PART_GOOD = "part_good"
	PART_BAD = "part_bad"

	INSTRUCTION = "work_instruction"
	FEEDBACK = "work_feedback"
	INSTRUCTION_STATE = "work_instruction_state"
	FEEDBACK_STATE = "work_feedback_state"

	ERRORS = "error_count"

	CONTAINER = "container_number"
	PART_NUMBER = "part_number"
	DESCRIPTION = "description"
	CURRENT_QTY = "current_container_qty"
	MAX_QUANTITY = "max_container_qty"
	PACKAGING_CMD = "packaging.cmd"


# ------------------------------------------------------------------ Worker IDs / constants

class SCRIPT_VAR(StrEnum):
	SCANNER_1 = "scanner1"
	PLC = "twincat"
	ITAC = "itac_main"

	ITAC_GET_PACK_INFO = "NOXPackaging.getPackInfo"
	ITAC_STATION = "6302028220"


class STEP(object):
	INIT = 0
	WAIT_SCAN = 10
	WAIT_BEFORE_MES = 15
	GET_PACKINFO = 20
	PLC_READ = 40
	REST_CALL = 50
	TCP_TEST = 60
	DONE = 70


# ------------------------------------------------------------------ Small helpers (script-local)

def ui_wait(ctx: PublicAutomationContext, instruction: str, feedback: str) -> None:
	ctx.ui.show(
		instruction=instruction,
		feedback=feedback,
		instruction_state="info",
		feedback_state="warn",
	)


def ui_ok(ctx: PublicAutomationContext, instruction: str, feedback: str) -> None:
	ctx.ui.show(
		instruction=instruction,
		feedback=feedback,
		instruction_state="ok",
		feedback_state="ok",
	)


def ui_error(ctx: PublicAutomationContext, instruction: str, feedback: str) -> None:
	ctx.ui.show(
		instruction=instruction,
		feedback=feedback,
		instruction_state="error",
		feedback_state="error",
	)
	ctx.ui.inc_state_int(UI_VAR.ERRORS, amount=1, default=0)


def apply_packinfo_to_ui(ctx: PublicAutomationContext, out_args: list) -> None:
	# Expected: [container, part_number, description, current_qty, max_qty, ...]
	container = out_args[0] if len(out_args) > 0 else ""
	part_number = out_args[1] if len(out_args) > 1 else ""
	description = out_args[2] if len(out_args) > 2 else ""
	current_qty = to_int(out_args[3] if len(out_args) > 3 else None, 0)
	max_qty = to_int(out_args[4] if len(out_args) > 4 else None, 0)

	ctx.set_state(UI_VAR.CONTAINER, container)
	ctx.set_state(UI_VAR.PART_NUMBER, part_number)
	ctx.set_state(UI_VAR.DESCRIPTION, description)
	ctx.set_state(UI_VAR.CURRENT_QTY, current_qty)
	ctx.set_state(UI_VAR.MAX_QUANTITY, max_qty)


# ------------------------------------------------------------------ Main

def main(ctx: PublicAutomationContext):
	"""
	Packaging demo chain (rewritten to be script-author friendly):

	- No time.sleep() (uses ctx.wait() non-blocking).
	- UI updates via ctx.ui.show(...) with named states (ok/warn/error/info/idle).
	- iTAC result parsing via ctx.workers.itac_expect_ok(...).
	- Robust int conversion via to_int(...).
	"""
	#ctx.set_cycle_time(1)

	step = ctx.step
	cmd = ctx.ui.consume_command(UI_VAR.PACKAGING_CMD)
	if cmd == "reset":
		ctx.log_info("Packaging command received: reset")
		ctx.goto(STEP.INIT)
		return
	if cmd == "stop":
		ctx.log_info("Packaging command received: stop")
		ui_wait(ctx, "Stopped by operator", "Press Start to continue")
		ctx.goto(STEP.WAIT_SCAN)
		return

	if step == STEP.INIT:

		ctx.set_step_desc("init")
		ui_wait(ctx, "Please scan a part", "Waiting for rail in...")
		ctx.goto(STEP.WAIT_SCAN)

	elif step == STEP.WAIT_SCAN:
		if cmd == "start":
			ctx.log_info("Packaging command received: start")
			ui_wait(ctx, "Please scan a part", "Preparing MES request...")
			ctx.goto(STEP.WAIT_BEFORE_MES)
			return
		return

	elif step == STEP.WAIT_BEFORE_MES:
		# Non-blocking delay (no sleep)
		if ctx.wait(1.0, STEP.GET_PACKINFO, desc="get pack info"):
			return

	elif step == STEP.GET_PACKINFO:
		ctx.set_step_desc("get pack info")
		ui_wait(ctx, "Please scan a part", "Requesting feedback from MES...")

		res = ctx.itac_custom_function(
			SCRIPT_VAR.ITAC,
			SCRIPT_VAR.ITAC_GET_PACK_INFO,
			in_args=[SCRIPT_VAR.ITAC_STATION, True],
			timeout_s=10.0,
		)

		norm = ctx.workers.itac_expect_ok(res)
		print(norm)
		if not norm.get("ok"):
			ui_error(ctx, "MES error", "getPackInfo failed: %s" % str(norm.get("error")))
			ctx.goto(STEP.PLC_READ)
			return

		out_args = norm.get("out_args", [])
		if not isinstance(out_args, list):
			ui_error(ctx, "MES error", "Invalid out_args type")
			ctx.goto(STEP.PLC_READ)
			return

		apply_packinfo_to_ui(ctx, out_args)
		ui_ok(ctx, "MES OK", "Pack info loaded")
		ctx.goto(STEP.PLC_READ)

	elif step == STEP.PLC_READ:
		ctx.set_step_desc("plc read")

		# These reads are non-blocking (latest cached values). For strict sync: use ctx.wait_plc(...)
		watchdog = ctx.read_plc(SCRIPT_VAR.PLC, "MAIN.watchdog", default=None)
		ip_addr = ctx.read_plc(SCRIPT_VAR.PLC, "MAIN.currentIPAddress", default=None)
		idx = ctx.read_plc(SCRIPT_VAR.PLC, "MAIN.idx", default=None)
		is_mqtt = ctx.read_plc(SCRIPT_VAR.PLC, "MAIN.isMQTTSetup", default=None)


		ctx.goto(STEP.REST_CALL)

	elif step == STEP.REST_CALL:
		ctx.set_step_desc("rest call")

		res = ctx.rest_post_json("book_serial", path="", body={"a": 1}, timeout_s=2.0)

		status = to_int(res.get("status"), 0)


		body = res.get("body", "")

		ctx.goto(STEP.TCP_TEST)

	elif step == STEP.TCP_TEST:
		ctx.set_step_desc("tcp test")

		# Fire-and-forget send + read latest message (depends on your tcp_client worker behavior)
		ctx.send_tcp(SCRIPT_VAR.SCANNER_1, "hello")
		msg = ctx.read_tcp(SCRIPT_VAR.SCANNER_1, default=None, decode=True)
		ctx.goto(STEP.DONE)


	elif step == STEP.DONE:
		ctx.set_step_desc("done -> reset")
		ui_ok(ctx, "Done", "Cycle finished")
		ctx.goto(STEP.INIT)
		ctx.goto(STEP.DONE)
		msg = "Something went really wrong"
		#  "info"  # "positive" | "negative" | "warning" | "info"
		#ctx.ui.notify(msg,type_="positive")
		print(1)
		ctx.log_error("ÄLARM!!!")
		#ctx.fail("fdsaf")
		ctx.log_success("super")

		ctx.goto(100)
	elif step == 100:
		res = ctx.read_com("scanner_1")
		print(res)

		ctx.goto(10)


	else:
		ctx.set_step_desc("unknown step=%s -> reset" % str(step))
		ui_error(ctx, "Script error", "Unknown step; resetting")
		ctx.goto(STEP.INIT)


# Export
main = main
