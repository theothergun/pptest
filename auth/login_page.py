from nicegui import ui, app
from auth.session import login


def register_login_page() -> None:
    @ui.page("/login")
    def login_view():
        with ui.card().classes("w-96 mx-auto mt-24"):
            ui.label("Login").classes("text-xl font-semibold")

            username = ui.input("Username").classes("w-full")
            password = ui.input("Password", password=True, password_toggle_button=True).classes("w-full")

            def do_login():
                # TODO: replace with real authentication (DB + hashed passwords)
                if not username.value:
                    ui.notify("Enter a username", type="negative")
                    return

                # Demo roles:
                roles = ("admin",) if username.value.lower() == "admin" else ("user",)

                login(username.value, roles)
                # always start on home
                app.storage.user["current_route"] = "home"
                #ui.run_javascript("window.location.href = '/?page=home'")
                ui.run_javascript("window.location.href = '/'")  # redirect to app

            ui.button("Sign in", on_click=do_login).props("color=primary").classes("w-full mt-2")
