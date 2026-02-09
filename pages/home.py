# pages/home.py
from nicegui import ui
from layout.action_bar.models import Action
from layout.action_bar.event_types import ActionBarEvent
from layout.context import PageContext
from layout.page_scaffold import build_page


def render(container: ui.element, ctx: PageContext) -> None:

    # listeners can be anywhere, but only need to be registered once per page build/render
    def on_action_clicked(action_id, action:Action):
        ui.notify(f"clicked: {action_id}")
        # example behavior: toggle active state
        if ctx.action_bar:
            ctx.action_bar.set_active(action_id, not action.is_active)

            # example: enable "save" after refresh is active
            if action_id == "refresh" and action.is_active:
                ctx.action_bar.set_enabled("save", True)

    #subscripte to the action clicked event
    ctx.bus.on(ActionBarEvent.CLICKED, on_action_clicked)

    def build_content(_parent: ui.element) ->None:
        with ui.column().classes("w-full"):
            with ui.card().classes("w-full self-end p-r-5"):
                ui.label("contains the counters")
                #first row containing the counters
            with ui.column():
                instruction_area = ui.label("instruction comes here")
                process_notification_are = ui.label("process state and error comes here")
            with ui.row():
                with ui.card():
                    ui.label("contains LTC data")
                with ui.card():
                    ui.label("contains VI data")
        ui.markdown("Main content grows to fill space.").classes("mt-4")

    build_page(ctx, container, title="Home", content=build_content,
               show_action_bar=True, on_action_clicked=on_action_clicked)


