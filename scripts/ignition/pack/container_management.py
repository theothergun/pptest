from __future__ import annotations

from loguru import logger

from services.worker_topics import WorkerTopics
from services.automation_runtime.context import PublicAutomationContext

script_name = "ignition.pack.container_management"
CREATE_CONTAINER_ERROR_POPUP_KEY = "create_and_activate_new_container"


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


def main(ctx: PublicAutomationContext):
	ctx.set_cycle_time(0.5)


	# Correct command channel for container_management view.
	cmd = ctx.ui.consume_command("packaging.cmd")
	#print(cmd)

	if cmd:
		logger.info(f"[{script_name}] command received: {cmd}")

	if cmd == "refresh":
		ctx.goto(100)
	elif cmd == "new":
		ctx.goto(200)


	step = ctx.step

	#print(step)
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
		result_text = payload.get("RESULT_TEXT")
		if result_code == 0:

			ctx.ui.set_state("part_number" , payload.get("DATA").get("PARTNUMBER"))
			ctx.ui.set_state("description", payload.get("DATA").get("DESCRIPTION"))
			ctx.ui.set_state("container_number" , payload.get("DATA").get("MATERIAL_BIN"))
			ctx.ui.set_state("max_container_qty", payload.get("DATA").get("QTY_TOTAL"))
			ctx.ui.set_state("current_container_qty", payload.get("DATA").get("QTY_CURR"))

			ctx.goto(101) # success
		else:
			ctx.set_state("get_container_result_text", result_text)
			ctx.goto(102)

	elif step == 101:
		ctx.ui.popup_wait_close()
		ctx.notify_positive("Successfully refreshed container")
		ctx.goto(0)

	elif step == 102: # fail
		ctx.notify_negative("Error refreshing container")
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


	elif step == 200:
		res = ctx.rest_post_json(
			"create_and_activate_new_container",
			"",
			{"asset_id": ctx.global_var("asset_id")},
			timeout_s=8.0,
		)
		ctx.ui.popup_wait_close()
		logger.info(f"[{script_name}] get_active_container raw response: {res}")
		payload = _extract_contract_payload(res)
		result_code = payload.get("RESULT_CODE")
		result_text = payload.get("RESULT_TEXT")
		if result_code == 0:
			ctx.goto(100)
		else:
			# popup_message is keyed + non-blocking; clear stale result/pending state
			# so the same popup can be shown again on repeated failures.
			ctx.ui.popup_clear(key=CREATE_CONTAINER_ERROR_POPUP_KEY)
			ctx.ui.popup_message(key=CREATE_CONTAINER_ERROR_POPUP_KEY, message=result_text)
			ctx.goto(0)


# Export
main = main
