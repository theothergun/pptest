from enum import StrEnum

from services.script_api import PublicAutomationContext, StateKeys
import random


from services.script_metadata import default_script_meta

SCRIPT_META = default_script_meta(__file__)

def get_random_float(min_value, max_value):
	return random.uniform(min_value, max_value)

def get_error_code():
	codes = ["NOK", "GL", "Pne", "DDL"]
	val = random.randint(0, 3)
	return codes[val]

def get_test_result(is_dummy: bool = False):
	if is_dummy:
		val = random.randint(1, 2)
		if val % 2 == 0:
			val = get_random_float(0.01, 0.12)
		else:
			val = get_random_float(0.45, 0.65)
	else:
		val = get_random_float(1.0, 3.4)

	return round(val, 3)


def analyse_test_result(value: float):
	return 3 if value < 1 or value > 2.6 else 1


# ------------------------------------------------------------------ UI keys (AppState)

class UI_VAR(StrEnum):
	INSTRUCTION = "work_instruction"
	FEEDBACK = "work_feedback"
	INSTRUCTION_STATE = "work_instruction_state"
	FEEDBACK_STATE = "ltc_error_status"
	ERRORS = "error_count"
	LTC_RESULT = "ltc_result"
	LEAK_RATE = "ltc_leak_rate"

	# optional "operator command" for this chain
	VISUAL_INSPECTION = "visual_inspection.cmd"


# Dummy flags in AppState (your ctx.state fields)
class DUMMY_VAR(StrEnum):
	IS_ENABLED = "dummy_is_enabled"  # shows/hides tool window
	IS_RUNNING = "dummy_test_is_running"  # spinner overlay
	RESULT_AVAILABLE = "dummy_result_available"  # trigger analyse_test_result
	PASSED = "dummy_test_passed"


# ------------------------------------------------------------------ Steps / constants

class STEP(object):
	IDLE = 0
	INIT = 1
	START_TEST = 20
	WORK_1 = 40
	WORK_2 = 60
	PUBLISH_RESULT = 80
	WAIT_END_OF_ANALYSE = 100
	SHOW_TEST_RESULT = 120
	DUMMY_DONE = 140


# ------------------------------------------------------------------ Small helpers (script-local)

def ui_show(ctx: PublicAutomationContext, instruction: str | None, feedback: str | None, state: int | None) -> None:
	if instruction is not None:
		ctx.set_state(UI_VAR.INSTRUCTION, instruction)
	if feedback is not None:
		ctx.set_state(UI_VAR.FEEDBACK, feedback)
	if state is not None:
		ctx.set_state(UI_VAR.FEEDBACK_STATE, state)


def ui_wait(ctx: PublicAutomationContext, instruction: str | None, feedback: str | None, state: int | None = 2) -> None:
	# ctx.ui.show(instruction=instruction,feedback=feedback,instruction_state="info",feedback_state="warn",)
	ui_show(ctx, instruction=instruction, feedback=feedback, state=state)


def ui_ok(ctx: PublicAutomationContext, instruction: str | None, feedback: str | None) -> None:
	# ctx.ui.show(instruction=instruction, feedback=feedback, instruction_state="info", feedback_state="ok",)
	ui_show(ctx, instruction=instruction, feedback=feedback, state=1)


def ui_error(ctx: PublicAutomationContext, instruction: str | None, feedback: str | None) -> None:
	# ctx.ui.show(instruction=instruction, feedback=feedback,	instruction_state="info", feedback_state="error",)
	ui_show(ctx, instruction=instruction, feedback=feedback, state=3)


# ctx.ui.inc_state_int(UI_VAR.ERRORS, amount=1, default=0)


def emit_dummy(ctx: PublicAutomationContext, key: DUMMY_VAR, value) -> None:
	"""
	Single place to update dummy flags.
	We use ctx.set_state(...) because that is what you already use everywhere else.

	If your framework requires bridge patches explicitly, replace this with:
		ctx.bridge.emit_patch(str(key.value), value)
	or whatever your script API provides.
	"""
	ctx.set_state(str(key.value), value)


# ------------------------------------------------------------------ Main

def main(ctx: PublicAutomationContext):
	"""
	Dummy demo chain (script-author friendly):

	- No time.sleep() (uses ctx.wait() non-blocking)
	- Drives AppState dummy flags:
		dummy_is_enabled
		dummy_test_is_running
		dummy_result_available
	- Lets controller / ExecutionState evaluate results when result_available flips True
	"""

	step = ctx.step
	cmd = ctx.ui.consume_command(UI_VAR.VISUAL_INSPECTION)

	# -------------------- global command handling --------------------
	if cmd == "stop":
		ctx.log_info("Dummy command received: stop")
		# stop running but keep window visible
		emit_dummy(ctx, DUMMY_VAR.IS_RUNNING, False)
		emit_dummy(ctx, DUMMY_VAR.RESULT_AVAILABLE, False)
		emit_dummy(ctx, DUMMY_VAR.PASSED, False)
		ui_wait(ctx, "Dummy stopped by operator", "Press Start to run again")
		ctx.goto(STEP.IDLE)
		return
	elif cmd == "start":
		ui_wait(ctx, "Dummy restarted by operator", "")
		ctx.goto(STEP.INIT)

	# -------------------- step machine --------------------
	if step == STEP.IDLE:
		return

	if step == STEP.INIT:
		ctx.set_step_desc("init")
		ui_wait(ctx, "Put a part to start the test", None, 0)
		ctx.data["error_code"] = get_error_code()
		if ctx.wait(2, STEP.START_TEST, "Waiting part ..."):
			return


	elif step == STEP.START_TEST:
		ctx.set_step_desc("start test")
		if ctx.get_state(DUMMY_VAR.IS_ENABLED):
			ui_wait(ctx, "Dummy demo", "Starting dummy test (spinner ON)...")
			emit_dummy(ctx, DUMMY_VAR.IS_RUNNING, True)
		else:
			ui_wait(ctx, "Production demo", "Starting test...")

		ctx.goto(STEP.WORK_1, "Test preparation")
		return


	elif step == STEP.WORK_1:
		ctx.set_step_desc("work 1")
		ui_wait(ctx, "Work in progress part_1", f"Simulating work... {ctx.cycle_count:.1f}s")

		# simulate some processing
		if ctx.wait(1.5, STEP.WORK_2, desc="work phase 2"):
			return

	elif step == STEP.WORK_2:
		ctx.set_step_desc("work 2")
		ui_wait(ctx, "Work in progress part_2", f"Still working... {ctx.cycle_count:.1f}s")
		ctx.set_state(UI_VAR.LEAK_RATE, get_test_result(ctx.get_state(DUMMY_VAR.IS_ENABLED)))
		st = STEP.PUBLISH_RESULT if ctx.get_state(DUMMY_VAR.IS_ENABLED) else STEP.SHOW_TEST_RESULT
		if ctx.wait(1.0, st, desc="publish result"):
			return

	elif step == STEP.PUBLISH_RESULT:
		ctx.set_step_desc("publish result")
		ui_wait(ctx, "Dummy demo", "Publishing result_available=True (controller will analyse)")
		emit_dummy(ctx, DUMMY_VAR.RESULT_AVAILABLE, True)
		ctx.goto(STEP.WAIT_END_OF_ANALYSE)
		return

	elif step == STEP.WAIT_END_OF_ANALYSE:
		ctx.set_step_desc("wait controller")
		ui_wait(ctx, "Dummy demo", "Analyzing the result...")

		if not ctx.get_state(DUMMY_VAR.RESULT_AVAILABLE) and not ctx.get_state(DUMMY_VAR.IS_RUNNING):
			state = 1 if ctx.get_state(DUMMY_VAR.PASSED) else 3
			if state == 1:
				ui_ok(ctx, "Test completed", "Test result: OK")
			else:
				ui_error(ctx, "Test completed", "Test result: %s"%ctx.data["error_code"])
			ctx.goto(STEP.DUMMY_DONE, desc="show result and state on main view")
			return

	elif step == STEP.SHOW_TEST_RESULT:
		state = analyse_test_result(ctx.get_state(UI_VAR.LEAK_RATE))
		if state == 1:
			ui_ok(ctx, "Test completed", "Ok")
			ctx.set_state(UI_VAR.LTC_RESULT, "OK")
		else:
			ui_error(ctx, "Test completed", ctx.data["error_code"])
			ctx.set_state(UI_VAR.LTC_RESULT, ctx.data["error_code"])

		if ctx.wait(state, STEP.INIT, desc="init step"):
			return

	elif step == STEP.DUMMY_DONE:
		ctx.set_step_desc("done -> reset")
		if not ctx.get_state(DUMMY_VAR.IS_ENABLED):
			ui_ok(ctx, "Dummy Test completed", "Dummy Test completed. Restarting in 3s...")
			ctx.log_success("Dummy demo cycle completed")
			ctx.ui.notify("Dummy demo run finished", type_="positive")

		if ctx.wait(3.0, STEP.INIT, desc="restart"):
			return

	else:
		ctx.set_step_desc("unknown step=%s -> reset" % str(step))
		ui_error(ctx, "Script error", "Unknown step; resetting")
		ctx.goto(STEP.INIT)


# Export
