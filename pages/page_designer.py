from __future__ import annotations

from nicegui import ui

from layout.context import PageContext
from layout.page_blocks import action_hint, kpi_tile, section_card, status_badge
from layout.page_scaffold import build_page
from layout.script_controls import ScriptButtonSpec, script_action_button, script_action_row, script_metadata_buttons
from services.script_actions import get_script_metadata
from services.worker_commands import ScriptWorkerCommands as ScriptCommands


DEMO_SCRIPT = "examples/page_designer_demo"


def render(container: ui.element, ctx: PageContext) -> None:
    metadata = get_script_metadata(ctx, DEMO_SCRIPT)

    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full gap-4"):
            with section_card(
                "View Builder Playground",
                "Use this page to test common layout blocks and script-bound buttons before building a production view.",
                icon="construction",
            ):
                with ui.row().classes("w-full flex-wrap gap-2 items-center"):
                    status_badge("PageDefinition", "ok")
                    status_badge("ScriptActionButton", "ok")
                    status_badge("SCRIPT_META", "ok")
                ui.markdown(
                    "Open the docs in `docs/building_views.md` and `docs/writing_scripts.md`, "
                    "or run `python scripts/create_page.py --name my_new_view`."
                ).classes("text-sm")

            with ui.row().classes("w-full flex-wrap gap-4"):
                kpi_tile("Cycle Time", "0.35 s", hint="Example KPI tile", icon="timer")
                kpi_tile("State", "Ready", hint="Use these blocks for station dashboards", icon="check_circle")
                kpi_tile("Errors", "0", hint="Bind this to ctx.state later", icon="warning")

            with section_card(
                "Reusable Script Buttons",
                "These buttons all call the script runtime through services/script_actions.py.",
                icon="smart_display",
            ):
                script_action_row(
                    ctx,
                    [
                        ScriptButtonSpec(label="Start Demo", command=ScriptCommands.START_CHAIN, script_name=DEMO_SCRIPT, color="positive", icon="play_arrow"),
                        ScriptButtonSpec(label="Pause Demo", command=ScriptCommands.PAUSE_CHAIN, script_name=DEMO_SCRIPT, color="warning", icon="pause"),
                        ScriptButtonSpec(label="Resume Demo", command=ScriptCommands.RESUME_CHAIN, script_name=DEMO_SCRIPT, color="primary", icon="play_arrow", outline=True),
                        ScriptButtonSpec(label="Stop Demo", command=ScriptCommands.STOP_CHAIN, script_name=DEMO_SCRIPT, color="negative", icon="stop"),
                        ScriptButtonSpec(label="Reload Demo", command=ScriptCommands.RELOAD_SCRIPT, script_name=DEMO_SCRIPT, color="info", icon="refresh", outline=True),
                    ],
                )

            with section_card(
                "Buttons From SCRIPT_META",
                "Define button metadata inside the script and render it directly in the page.",
                icon="inventory_2",
            ):
                if metadata:
                    ui.label(str(metadata.get("title") or DEMO_SCRIPT)).classes("text-base font-semibold")
                    description = str(metadata.get("description") or "")
                    if description:
                        ui.label(description).classes("text-sm text-[var(--text-secondary)]")
                script_metadata_buttons(ctx, DEMO_SCRIPT)

            with ui.grid(columns=2).classes("w-full gap-4"):
                action_hint(
                    "Suggested Page Workflow",
                    [
                        "1. Generate a page with scripts/create_page.py.",
                        "2. Register the route in pages/builtin_pages.py or config custom_routes.",
                        "3. Compose the layout with layout/page_blocks.py helpers.",
                        "4. Bind buttons with layout/script_controls.py.",
                    ],
                )
                action_hint(
                    "Suggested Script Workflow",
                    [
                        "1. Create a script with main(ctx).",
                        "2. Add SCRIPT_META if the UI should render its buttons.",
                        "3. Use ctx.ui / ctx.flow / ctx.workers inside the script.",
                        "4. Start it from a view with ScriptButtonSpec or services/script_actions.py.",
                    ],
                )

            with section_card("Direct Button Example", "Use this when you only need one button.", icon="ads_click"):
                script_action_button(
                    ctx,
                    ScriptButtonSpec(
                        label="Run Demo Once",
                        command=ScriptCommands.START_CHAIN,
                        script_name=DEMO_SCRIPT,
                        color="primary",
                        icon="bolt",
                    ),
                )

    build_page(
        ctx,
        container,
        title="Page Designer",
        content=build_content,
        show_action_bar=False,
    )
