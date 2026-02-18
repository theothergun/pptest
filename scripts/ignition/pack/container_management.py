from __future__ import annotations

from loguru import logger

from services.worker_topics import WorkerTopics
from services.workers.stepchain.context import PublicStepChainContext

script_name = "ignition.pack.container_management"


def _extract_contract_payload(res: dict) -> dict:
	"""
	Accept both shapes:
	1) direct contract: {"RESULT_CODE": ..., "DATA": ...}
	2) rest worker envelope: {"json": {"RESULT_CODE": ...}, ...}
	"""
	if not isinstance(res, dict):
		return {}
	if "RESULT_CODE" in res:
		return res
	js = res.get("json")
	if isinstance(js, dict) and "RESULT_CODE" in js:
		return js
	return {}


def main(ctx: PublicStepChainContext):
	ctx.set_cycle_time(0.5)


	# Correct command channel for container_management view.
	cmd = ctx.ui.consume_command("packaging.cmd")
	print(cmd)

	if cmd:
		logger.info(f"[{script_name}] command received: {cmd}")

	if cmd == "refresh":
		ctx.goto(100)

	step = ctx.step
	print(step)
	if step == 0:
		pass
	elif step == 100:
		res = ctx.rest_post_json(
			"get_active_container",
			"",
			{"asset_id": ctx.global_var("asset_id")},
			timeout_s=8.0,
		)
		logger.info(f"[{script_name}] get_active_container raw response: {res}")

		payload = _extract_contract_payload(res)
		result_code = payload.get("RESULT_CODE")
		result_text = str(payload.get("RESULT_TEXT", "") or "")
		print("*" * 50)
		print(result_code)
		print(payload.get("RESULT_CODE"))
		print("*" * 50)
		if result_code != 0:
			ctx.ui.notify(
				f"get_active_container failed: code={result_code} text={result_text}",
				type_="warning",
			)
			ctx.goto(101) # success
		else:
			ctx.goto(102)
	elif step == 101:
		ctx.ui.popup_wait_close()
		ctx.goto(0)
	elif step == 102: # fail
		ctx.ui.popup_message("container" , message="Something went wrong" )
		ctx.ui.popup_wait_close()
		ctx.goto(0)

	elif step == 105:

		ctx.workers.publish(
			topic=WorkerTopics.TOPIC_MODAL_CLOSE,
			source="ScriptWorker",
			source_id="packaging",
			key="packaging.wait",
		)

		ctx.set_step_desc("active container mapped to app_state")


# Export
main = main
