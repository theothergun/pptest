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


def _contains(value: str, query: str) -> bool:
    return query in str(value or "").lower()


def _filter_containers(rows: list[dict], query: str) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return list(rows or [])
    out: list[dict] = []
    for row in rows or []:
        if (
            _contains(row.get("material_bin", ""), q)
            or _contains(row.get("part_number", ""), q)
            or _contains(row.get("current_qty", ""), q)
        ):
            out.append(row)
    return out


def _filter_serials(rows: list[dict], query: str) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return list(rows or [])
    out: list[dict] = []
    for row in rows or []:
        if _contains(row.get("serial_number", ""), q):
            out.append(row)
    return out


def main(ctx: PublicStepChainContext):
    ctx.set_cycle_time(0.2)

    step = ctx.step
    if step == 0:
        containers = _demo_container_rows()
        serials = _demo_serial_rows()
        ctx.vars.set("container_rows_all", containers)
        ctx.vars.set("serial_rows_all", serials)
        ctx.view.container_management.set_search_query("AB")
        ctx.view.container_management.set_container_rows(containers)
        ctx.view.container_management.set_serial_rows(serials)
        ctx.view.container_management.set_active_container("SP08000001AB")
        ctx.view.container_management.set_container_selected("SP08000001AB")
        ctx.set_step_desc("container management pseudo script ready")
        ctx.goto(10)
        return

    if step != 10:
        ctx.goto(10)
        return

    payload = ctx.view.container_management.consume_payload()
    if payload is None:
        ctx.set_step_desc("waiting for container management action")
        return

    cmd = str(payload.get("cmd", "") or "").lower()
    query = str(ctx.view.container_management.get_state("container_mgmt_search_query", "") or "")
    containers_all = list(ctx.vars.get("container_rows_all", _demo_container_rows()) or [])
    serials_all = list(ctx.vars.get("serial_rows_all", _demo_serial_rows()) or [])

    if cmd in ("search_container", "search"):
        rows = _filter_containers(containers_all, query)
        ctx.view.container_management.set_container_rows(rows)
        ctx.set_step_desc("container search updated")
        return

    if cmd == "search_serial":
        rows = _filter_serials(serials_all, query)
        ctx.view.container_management.set_serial_rows(rows)
        ctx.set_step_desc("serial search updated")
        return

    if cmd == "activate":
        selected = str(ctx.view.container_management.get_state("container_mgmt_container_selected", "") or "-")
        ctx.view.container_management.set_active_container(selected)
        ctx.set_step_desc("activated container %s" % selected)
        return

    if cmd == "refresh":
        containers_all = _demo_container_rows()
        serials_all = _demo_serial_rows()
        ctx.vars.set("container_rows_all", containers_all)
        ctx.vars.set("serial_rows_all", serials_all)
        ctx.view.container_management.set_tables(container_rows=containers_all, serial_rows=serials_all)
        ctx.set_step_desc("refreshed pseudo data")
        return

    if cmd == "remove_serial":
        serial = str(payload.get("serial", "") or "")
        if serial:
            serials_all = [row for row in serials_all if str(row.get("serial_number", "")) != serial]
        elif serials_all:
            serials_all = serials_all[1:]
        ctx.vars.set("serial_rows_all", serials_all)
        ctx.view.container_management.set_serial_rows(serials_all)
        ctx.set_step_desc("removed serial %s (pseudo)" % (serial or "<first>"))
        return

    if cmd == "remove_all":
        ctx.vars.set("serial_rows_all", [])
        ctx.view.container_management.set_serial_rows([])
        ctx.set_step_desc("cleared all serials (pseudo)")
        return

    ctx.set_step_desc("ignored command: %s" % cmd)


# Export
main = main
