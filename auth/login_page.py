import asyncio

from nicegui import ui, app, run

from auth.auth_service import authenticate_user
from auth.session import login
from loguru import logger
from services.app_config import get_app_config


def register_login_page() -> None:
    @ui.page("/login")
    def login_view():
        ui.add_head_html(
            """
            <style>
            @keyframes login-spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            .login-spin {
                animation: login-spin 1s linear infinite;
            }
            </style>
            """
        )
        with ui.card().classes("w-96 mx-auto mt-24"):
            ui.label("Login").classes("text-xl font-semibold")

            username = ui.input("Username").classes("w-full")
            password = ui.input("Password", password=True, password_toggle_button=True).classes("w-full")
            submit_state = {"busy": False}
            with ui.dialog().props("persistent") as login_progress_dialog:
                with ui.card().classes("w-72 items-center gap-3 py-6"):
                    ui.icon("login").classes("text-primary text-4xl login-spin")
                    ui.label("Logging in ...").classes("text-base font-medium")

            async def do_login():
                if submit_state["busy"]:
                    return
                submit_state["busy"] = True
                login_button.disable()
                login_progress_dialog.open()
                success = False

                entered_username = str(username.value or "").strip()
                logger.info(
                    "Login page submit: username='{}' mode='{}'",
                    entered_username,
                    str(get_app_config().auth.validation_mode or "local"),
                )

                try:
                    await asyncio.sleep(0)
                    ok, roles, message, profile = await run.io_bound(
                        authenticate_user,
                        entered_username,
                        str(password.value or ""),
                    )
                    if not ok:
                        logger.warning("Login page rejected: username='{}' reason='{}'", entered_username, message or "Login failed")
                        ui.notify(message or "Login failed", type="negative")
                        return

                    forename = str((profile or {}).get("forename", "") or "")
                    lastname = str((profile or {}).get("lastname", "") or "")
                    login(entered_username, roles, forename=forename, lastname=lastname)
                    logger.success(
                        "Login page success: username='{}' forename='{}' lastname='{}' roles={}",
                        entered_username,
                        forename,
                        lastname,
                        list(roles),
                    )
                    app.storage.user["current_route"] = get_app_config().ui.navigation.main_route or "home"
                    success = True
                    ui.run_javascript("window.location.href = '/'")
                except Exception:
                    logger.exception("Login page error while authenticating username='{}'", entered_username)
                    ui.notify("Login failed", type="negative")
                finally:
                    if not success:
                        login_progress_dialog.close()
                        submit_state["busy"] = False
                        login_button.enable()

            async def on_password_enter(_event) -> None:
                await do_login()

            login_button = ui.button("Sign in", on_click=do_login).props("color=primary").classes("w-full mt-2")
            password.on("keydown.enter", on_password_enter)
