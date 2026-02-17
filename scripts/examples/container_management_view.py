from __future__ import annotations

import time
from services.workers.stepchain.context import PublicStepChainContext


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


def main(ctx: PublicStepChainContext):
	"""
	Example script for container_management view.
	"""
	ctx.set_cycle_time(0.2)

	step = ctx.step
	if step == 0:
		ctx.view.container_management.set_search_query("AB")
		ctx.view.container_management.set_container_rows(_demo_container_rows())
		ctx.view.container_management.set_serial_rows(_demo_serial_rows())
		ctx.view.container_management.set_active_container("SP08000001AB")
		ctx.view.container_management.set_container_selected("SP08000001AB")
		ctx.set_step_desc("container management demo ready")
		ctx.goto(10)
		return

	if step == 10:
		payload = ctx.view.container_management.consume_payload()
		if payload is None:
			ctx.set_step_desc("Waiting for container management action...")
			return
		cmd = str(payload.get("cmd", "") or "").lower()

		if cmd in ("search_container", "search"):
			ctx.view.container_management.set_container_rows(_demo_container_rows())
			ctx.set_step_desc("container search updated")
			return

		if cmd == "search_serial":
			ctx.view.container_management.set_serial_rows(_demo_serial_rows())
			ctx.set_step_desc("serial search updated")
			return

		if cmd == "activate":
			value = ctx.view.container_management.get_state("container_mgmt_container_selected", "")
			ctx.view.container_management.set_active_container(str(value or "-"))
			ctx.set_step_desc("activated container")
			return

		if cmd == "refresh":
			ctx.view.container_management.set_serial_rows(_demo_serial_rows())
			ctx.set_step_desc("refreshed list")
			return

		if cmd == "remove_serial":
			serial = str(payload.get("serial", "") or "")
			rows = _demo_serial_rows()
			if serial:
				rows = [r for r in rows if str(r.get("serial_number")) != serial]
			else:
				rows = rows[1:]
			ctx.view.container_management.set_serial_rows(rows)
			ctx.set_step_desc("removed serial=%s (demo)" % (serial or "first"))
			return

		if cmd == "remove_all":
			ctx.view.container_management.set_serial_rows([])
			ctx.set_step_desc("cleared all serials (demo)")
			return


# Export
main = main
