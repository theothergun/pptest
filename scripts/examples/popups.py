from services.script_api import PublicAutomationContext
import json
from enum import StrEnum

from services.automation_runtime.apis.api_utils import to_int


# ------------------------------------------------------------------ Main

def main(ctx: PublicAutomationContext):
	#ctx.set_cycle_time(1)

	step = ctx.step
	if step == 0:
		ctx.ui.popup_clear('delete_wo')
		ctx.goto(10)

	elif step == 10: # confirm popup
		res = ctx.ui.popup_confirm(
			"delete_wo",
			"Delete workorder?",
			title="Confirm delete",
			ok_text="Delete",
			cancel_text="Cancel",
		)
		if res:
			ctx.goto(20)

	elif step == 20:
		res = ctx.ui.popup_message(
			"wo_deleted",
			"You deleted my workoder :´(",
			title="Workorder delete confirmation",
			buttons=[
				{"id": "retry", "text": "Retry"},
				{"id": "cancel", "text": "Cancel"},
			],
			wait_step_desc="Device offline - waiting for operator...",
		 )
		if res:
			if res['clicked'] == "cancel":
				ctx.goto(99)
			if res['clicked'] == "retry":
				ctx.goto(0)


		#res = ctx.ui.popup_message(
		#	"device_lost",
		#	"Connection to device lost",
		#	title="Device",
		#	buttons=[
		#		{"id": "retry", "text": "Retry"},
		#		{"id": "cancel", "text": "Cancel"},
		#	],
		#	wait_step_desc="Device offline - waiting for operator...",
		#)
		#ans = ctx.ui.popup_input_text("enter_comment", "Please type in a text message", title="Comment")
		#if ans is None:
		#	return
		#if not ans.get("ok"):
		#	ctx.goto(0)
		#	return
		#comment = str(ans.get("value") or "")

		#print(comment)
		#return

		#ans = ctx.ui.popup_input_number("enter_qty", "Please type in a number", title="Quantity", default=1)
		#if ans is None:
		#	return
		#if not ans.get("ok"):
		#	return
		#qty_raw = ans.get("value")
		#qty = int(qty_raw) if qty_raw is not None else 0
		#print(qty)
		#ctx.ui.popup_clear("choose_mode")
		#ans = ctx.ui.popup_choose(
		#	"choose_mode",
		#	"Please choose from this list",
		#	title="Mode",
		#	options=[
		#		{"id": "auto", "text": "Automatic"},
		#		{"id": "manual", "text": "Manual"},
		#		{"id": "service", "text": "Service"},
		#	],
		#	default="auto",
		#)


# Export
main = main
