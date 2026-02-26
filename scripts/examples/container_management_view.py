from __future__ import annotations
from services.script_api import PublicAutomationContext, StateKeys

import time


def _demo_container_rows() -> list[dict]:
	return [
		{"material_bin": "SP08000000AB", "part_number": "3618278074", "current_qty": "130/130"},
		{"material_bin": "SP08000001AB", "part_number": "3617836139", "current_qty": "8/45"},
		{"material_bin": "SP08000002AB", "part_number": "2618580110", "current_qty": "8/60"},
		{"material_bin": "SP08000003AB", "part_number": "3617978031", "current_qty": "30/30"},
	]


def _demo_serial_rows() -> list[dict]:
	now = time.strftime("%b %d, %Y %I:%M %p")
	return [
		{"serial_number": "253110828007683617836139", "created_on": now},
		{"serial_number": "253110828008283617836139", "created_on": now},
		{"serial_number": "253110828007793617836139", "created_on": now},
		{"serial_number": "253110828007743617836139", "created_on": now},
	]


def main(ctx: PublicAutomationContext):
	"""
	Example script for container_management using generic ctx.ui/state APIs.
	"""
	ctx.set_cycle_time(0.2)

	step = ctx.step
	if step == 0:
		ctx.set_state(StateKeys.container_mgmt_search_query, "AB")
		ctx.set_state(StateKeys.container_mgmt_container_rows, _demo_container_rows())
		ctx.set_state(StateKeys.container_mgmt_serial_rows, _demo_serial_rows())
		ctx.set_state(StateKeys.container_mgmt_active_container, "SP08000001AB")
		ctx.set_state(StateKeys.container_mgmt_container_selected, "SP08000001AB")
		ctx.set_step_desc("container management demo ready")
		ctx.goto(10)
		return

	if step == 10:
		payload = ctx.ui.consume_payload("container_management.cmd")
		if payload is None:
			ctx.set_step_desc("Waiting for container management action...")
			return
		cmd = str(payload.get("cmd", "") or "").lower()

		if cmd in ("search_container", "search"):
			ctx.set_state(StateKeys.container_mgmt_container_rows, _demo_container_rows())
			ctx.set_step_desc("container search updated")
			return

		if cmd == "search_serial":
			ctx.set_state(StateKeys.container_mgmt_serial_rows, _demo_serial_rows())
			ctx.set_step_desc("serial search updated")
			return

		if cmd == "activate":
			value = ctx.get_state(StateKeys.container_mgmt_container_selected, "")
			ctx.set_state(StateKeys.container_mgmt_active_container, str(value or "-"))
			ctx.set_step_desc("activated container")
			return

		if cmd == "refresh":
			ctx.set_state(StateKeys.container_mgmt_serial_rows, _demo_serial_rows())
			ctx.set_step_desc("refreshed list")
			return

		if cmd == "remove_serial":
			serial = str(payload.get("serial", "") or "")
			rows = _demo_serial_rows()
			if serial:
				rows = [r for r in rows if str(r.get("serial_number")) != serial]
			else:
				rows = rows[1:]
			ctx.set_state(StateKeys.container_mgmt_serial_rows, rows)
			ctx.set_step_desc("removed serial=%s (demo)" % (serial or "first"))
			return

		if cmd == "remove_all":
			ctx.set_state(StateKeys.container_mgmt_serial_rows, [])
			ctx.set_step_desc("cleared all serials (demo)")
			return


# Export
main = main
