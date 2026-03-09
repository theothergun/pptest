# pages/home.py
from nicegui import ui
from layout.action_bar.models import Action
from layout.action_bar.event_types import ActionBarEvent
from layout.context import PageContext
from layout.page_actions import bind_action_map
from layout.page_blocks import kpi_tile, section_card, status_badge
from layout.page_scaffold import build_page
from services.i18n import t
from loguru import logger


def render(container: ui.element, ctx: PageContext) -> None:
    logger.debug(f"[render] - render_home_page")

    def on_action_clicked(_ctx: PageContext, action_id: str, action: Action) -> None:
        logger.info(f"[on_action_clicked] - action_clicked - action_id={action_id} active={action.is_active}")
        ui.notify(t("home.notify.clicked", "clicked: {action_id}", action_id=action_id))
        if ctx.action_bar:
            ctx.action_bar.set_active(action_id, not action.is_active)
            if action_id == "start" and action.is_active:
                ctx.action_bar.set_enabled("save", True)

    action_handler = bind_action_map(
        ctx,
        {
            "start": on_action_clicked,
            "save": on_action_clicked,
            "delete": on_action_clicked,
        },
    )
    def build_content(_parent: ui.element) -> None:
        with ui.column().classes("w-full gap-4"):
            with section_card(
                t("home.title", "Home"),
                t("home.tooltip.counters", "Production counters summary"),
                icon="dashboard",
            ):
                with ui.row().classes("w-full flex-wrap gap-4"):
                    kpi_tile(t("home.counters", "Counters"), "24", hint="Example KPI", icon="counter_1")
                    kpi_tile(t("home.ltc_data", "LTC"), "Online", hint="Replace with live values", icon="memory")
                    kpi_tile(t("home.vi_data", "VI"), "Ready", hint="Replace with live values", icon="visibility")

            with section_card(
                t("home.instruction", "Instruction comes here"),
                t("home.process_state", "Process state and error comes here"),
                icon="list_alt",
            ):
                with ui.row().classes("w-full items-center gap-2"):
                    status_badge("Ready", "ok")
                    status_badge("No errors", "info")
        ui.markdown(t("home.main_content", "Main content grows to fill space.")).classes("mt-4")

    build_page(
        ctx,
        container,
        title=t("home.title", "Home"),
        content=build_content,
        show_action_bar=True,
        on_action_clicked=action_handler,
    )
