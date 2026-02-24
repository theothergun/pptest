# pages/home.py
import queue

from nicegui import ui
from loguru import logger

from layout.action_bar.models import Action
from layout.context import PageContext
from layout.page_scaffold import build_page
from pages.visual_inspection.dialog import create_failure_catalogue_dialog
from services.ui.view_action import make_action_event
from services.ui.registry import UiActionName, UiEvent, ViewName

BG_Q_CLASSES = {"bg-positive", "bg-warning", "bg-negative", "bg-info"}

def render(container: ui.element, ctx: PageContext) -> None:
    dialog, open_catalogue = create_failure_catalogue_dialog(ctx)



    # --- lifecycle management (same pattern as your Scripts Lab page) ---
    page_timers: list = []
    #page_subs: list = [] # use it in case you have multiple individual subscription
    sub_state = ctx.bridge.subscribe_many(["state.ltc_error_status","state.vc_error_status"])

    def add_timer(*args, **kwargs):
        t = ui.timer(*args, **kwargs)
        page_timers.append(t)
        return t

    def cleanup() -> None:
        try:
           sub_state.close()
        except Exception:
            logger.warning("Failed to close visual-inspection state subscription during cleanup")

        for t in page_timers:
            try:
                t.cancel()
            except Exception:
                logger.warning("Failed to cancel visual-inspection timer during cleanup")
        page_timers[:] = []

    ctx.state._page_cleanup = cleanup
    ui.context.client.on_disconnect(cleanup)

    # listeners can be anywhere, but only need to be registered once per page build/render
    def on_action_clicked(action_id, action:Action):
        action_event = make_action_event(view=ViewName.VI_HOME, name=UiActionName(str(action_id)), event=UiEvent.CLICK)
        action_name = action_event["name"]

        # example behavior: toggle active state
        if ctx.action_bar:
            #ctx.action_bar.set_active(action_id, not action.is_active)

            # example: enable "save" after refresh is active
            if action_name == UiActionName.START_STOP.value:
                ui.notify(f"clicked: {action_id}")
                #ctx.action_bar.set_active(action_id, not action.is_active)
                ctx.action_bar.update(action_id,active= not action.is_active)
                ctx.action_bar.set_enabled("unlock", not action.is_active)

            if action_name == UiActionName.LTC_STATUS.value:
                ctx.set_state_and_publish("ltc_error_status", (ctx.state.ltc_error_status+1)%4)
                ui.notify(f"new ltc status = {ctx.state.ltc_error_status}")

            if action_name == UiActionName.VC_STATUS.value:
                #ctx.state.vc_error_status = (ctx.state.vc_error_status+1)%4
                ctx.set_state_and_publish("vc_error_status", (ctx.state.vc_error_status + 1) % 4)
                ui.notify(f"new vc status = {ctx.state.vc_error_status}")

            if action_name == UiActionName.FAILURE_CATALOGUE.value:
                ui.notify("failures")
                open_catalogue(sn="1234567", pn="ABC-999")

            if action_name == UiActionName.UNLOCK.value:
                #ctx.state.ltc_leak_rate +=1
                ctx.set_state_and_publish("ltc_leak_rate", (ctx.state.vc_error_status + 1) % 4)

    def build_content(_parent: ui.element) ->None:
        #Root: 2 rows (top / middle / bottom)
        with ui.column().classes("w-full h-screen box-border gap-4 px-6 pb-4 pt-0 overflow-hidden"):
            # ── Row 1: Centered text block, Counters card aligned right ─────────────────────────────────────
            with ui.row().classes("w-full flex-1 relative"):
                # Two labels, stacked, relatively centered
                with ui.column().classes("absolute left-1/2 top-10 -translate-x-1/2 -translate-y-1/2 items-center gap-3"):
                    work_instruction = ui.label() \
                        .classes('text-lg font-semibold text-center text-black')
                    work_instruction.bind_text_from(ctx.state, "work_instruction", backward=lambda n:str(n))
                    work_instruction.classes("bg-primary min-w-[500px] py-2")

                    work_progress = ui.label() \
                        .classes('text-base text-center text-black')
                    work_progress.bind_text_from(ctx.state, "work_feedback", backward= lambda n:str(n))
                    work_progress.classes("bg-info min-w-[500px] py-2")

                # Counters card aligned right
                with ui.row().classes("w-full items-start"):
                    with ui.card().classes("ml-auto w-[180px] p-0"):
                        # header bar (full width)
                        with ui.row().classes("w-full h-[35px] bg-gray-200 px-3 py-1 rounded-t"):
                            ui.label("Counters").classes("text-lg font-semibold mb-1")
                        # body
                        body = ui.row()
                        _add_card_entries(body, {"part_good": "Good", "part_bad": "Bad", "part_total": "Total"})


            # ── Row 2: Left card, optional center picture section, right card ─────────
            with ui.row().classes('w-full h-[180px] items-stretch justify-between gap-6'):

                ltc_card = ui.card().classes("w-[350px] h-full p-0")
                with ltc_card:
                    #header
                    with ui.row().classes("w-full h-[35px] bg-gray-200 px-3 py-1 rounded-t"):
                        ui.label("Leak Test").classes("text-lg font-semibold")
                    # body
                    body = ui.row()
                    _add_card_entries(body, {"ltc_dmc": "Serial number", "ltc_status": "Progress",
                        "ltc_leak_rate": "Leak rate", "ltc_result": "Result"}, "text-black")

                # Center section (can be shown/hidden later)
                center_section = ui.column().classes('flex-1 items-center justify-center')
                with center_section:
                    ui.label('Picture area').classes('text-gray-500')
                # Example placeholder; swap to ui.image('...') later
                # ui.image('path_or_url').classes('max-h-64 object-contain')

                vc_card = ui.card().classes("w-[350px] h-full p-0 ml-auto")
                with vc_card:
                    #header
                    with ui.row().classes("w-full h-[35px] bg-gray-200 px-3 py-1 rounded-t"):
                        ui.label("Visual control").classes("text-lg font-semibold")
                    # body
                    body = ui.row()
                    _add_card_entries(body, {"vc_dmc": "Serial number", "vc_result": "Result"}, "text-black")

        # update ltc color
        def update_ltc_color(status=0) -> None:
            ltc_color = _get_bg_color(status)
            update_bg_color([work_progress, ltc_card], ltc_color)

        # update vc color
        def update_vc_color(status=0) -> None:
            vc_color = _get_bg_color(status)
            update_bg_color([vc_card], vc_color)

        def update_bg_color(elements: list[ui.element], color: str):
            for elem in elements:
                elem.classes(remove=" ".join(BG_Q_CLASSES))
                elem.classes(color)

        def initialize_colors():
            update_ltc_color(status= ctx.state.ltc_error_status)
            update_vc_color(status=ctx.state.vc_error_status)

        #read the bus to get any available changes and make extra reaction to them like updating styles
        def _drain_bus() -> None:
            while True:
                try:
                    msg = sub_state.queue.get_nowait()
                    key = msg.topic.replace("state.", "")
                    if key == "ltc_error_status":
                        update_ltc_color(msg.payload[key])
                    if key == "vc_error_status":
                        update_vc_color(msg.payload[key])

                    #ui.notify(msg)
                except queue.Empty:
                    break

        add_timer(0.1, _drain_bus)

        initialize_colors()



    def _add_card_entries(parent: ui.element, data:dict[str, str], text_color: str = "text-gray-600"):
        with parent.classes('w-full gap-2 px-1 py-1'):
            for key, label_text in data.items():
                with ui.row().classes('w-full items-center justify-between leading-none px-2 pb-2'):
                    ui.label(label_text).classes(f'text-[15px] {text_color} m-0 leading-none')
                    ui.label().classes('text-xl font-bold m-0 leading-none') \
                        .bind_text_from(ctx.state, key, backward=lambda n: str(n))

    def _get_bg_color(status:int):
        #status: 0 = init, 1= working, 2 = success, 3 = error
        # bg-orange-8 = working bg-red-8 = error
        return "bg-%s"%("positive" if status == 1 else "warning" if status == 2\
            else "negative" if status == 3 else "info")


    build_page(ctx, container, title="Home", content=build_content,
               show_action_bar=True, on_action_clicked=on_action_clicked)

