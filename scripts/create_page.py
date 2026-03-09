from __future__ import annotations

import argparse
from pathlib import Path


PAGE_TEMPLATE = '''from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from layout.page_blocks import section_card, kpi_tile
from layout.page_scaffold import build_page
from layout.script_controls import ScriptButtonSpec, script_action_row
from services.worker_commands import ScriptWorkerCommands as ScriptCommands


SCRIPT_NAME = "{script_name}"


def render(container: ui.element, ctx: PageContext) -> None:
    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full gap-4"):
            with section_card(
                "{title}",
                "Replace this text with the actual operator workflow.",
                icon="dashboard",
            ):
                with ui.row().classes("w-full flex-wrap gap-4"):
                    kpi_tile("Status", "Ready", hint="Example KPI tile", icon="check_circle")
                    kpi_tile("Order", "-", hint="Bind real values later", icon="assignment")

            with section_card(
                "Script Actions",
                "Bind page buttons to automation scripts with ScriptButtonSpec.",
                icon="smart_display",
            ):
                script_action_row(
                    ctx,
                    [
                        ScriptButtonSpec(label="Start", command=ScriptCommands.START_CHAIN, script_name=SCRIPT_NAME, color="positive", icon="play_arrow"),
                        ScriptButtonSpec(label="Stop", command=ScriptCommands.STOP_CHAIN, script_name=SCRIPT_NAME, color="negative", icon="stop", outline=True),
                    ],
                )

    build_page(
        ctx,
        container,
        title="{title}",
        content=build_content,
        show_action_bar=False,
    )
'''


SCRIPT_TEMPLATE = '''from __future__ import annotations

from services.script_api import PublicAutomationContext


SCRIPT_META = {{
    "title": "{title}",
    "description": "Describe what this script controls.",
    "buttons": [
        {{
            "id": "start",
            "label": "Start",
            "icon": "play_arrow",
            "color": "positive",
            "command": "script.start_chain",
        }},
        {{
            "id": "stop",
            "label": "Stop",
            "icon": "stop",
            "color": "negative",
            "command": "script.stop_chain",
        }},
    ],
}}


def main(ctx: PublicAutomationContext) -> None:
    ctx.publish_changes(True)

    if ctx.step == 0:
        ctx.set_step_desc("Initialize")
        ctx.goto(10, "Running")
        return

    if ctx.step == 10:
        ctx.set_step_desc("Running")
        ctx.set_state("{route_key}_status", "running")
        if ctx.wait(1.0, 20, "Loop complete"):
            return
        return

    if ctx.step == 20:
        ctx.set_step_desc("Loop complete")
        ctx.goto(10, "Running")
'''


def safe_name(value: str) -> str:
    return "_".join(part for part in str(value or "").strip().replace("-", "_").split("_") if part)


def title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in safe_name(value).split("_"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a NiceGUI page and matching script template.")
    parser.add_argument("--name", required=True, help="Page file name without .py")
    parser.add_argument("--title", help="Human-readable page title")
    parser.add_argument("--pages-dir", default="pages")
    parser.add_argument("--scripts-dir", default="scripts")
    parser.add_argument("--script-name", help="Script name to reference from the page")
    args = parser.parse_args()

    name = safe_name(args.name)
    if not name:
        raise SystemExit("Invalid page name")

    title = args.title or title_case(name)
    route_key = name
    script_name = args.script_name or f"generated/{name}"

    page_path = Path(args.pages_dir) / f"{name}.py"
    script_path = Path(args.scripts_dir) / "generated" / f"{name}.py"

    if page_path.exists() or script_path.exists():
        raise SystemExit(f"Refusing to overwrite existing files: {page_path} / {script_path}")

    page_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True, exist_ok=True)

    page_path.write_text(PAGE_TEMPLATE.format(title=title, script_name=script_name), encoding="utf-8")
    script_path.write_text(SCRIPT_TEMPLATE.format(title=title, route_key=route_key), encoding="utf-8")

    print(f"Created page: {page_path}")
    print(f"Created script: {script_path}")
    print("Add the route in pages/builtin_pages.py or config.ui.navigation.custom_routes.")
    print(f"Suggested route key: {route_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
