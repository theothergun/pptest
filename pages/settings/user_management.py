from __future__ import annotations

from typing import Any

from nicegui import ui

from auth.passwords import hash_password
from layout.context import PageContext
from services.app_config import get_app_config, save_app_config


_AUTH_MODE_OPTIONS = {
    "local": "Local users only",
    "rest_api": "REST API only",
    "itac": "iTAC only",
    "local_or_rest_api": "Local first, then REST API",
    "local_or_itac": "Local first, then iTAC",
}


def _parse_roles(value: str) -> list[str]:
    return [r.strip() for r in str(value or "").split(",") if r.strip()]


def _users(cfg) -> list[dict[str, Any]]:
    users = cfg.auth.users if isinstance(cfg.auth.users, list) else []
    out: list[dict[str, Any]] = []
    for item in users:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username", "")).strip()
        if not username:
            continue
        roles = item.get("roles", [])
        roles_list = [str(r).strip() for r in roles] if isinstance(roles, list) else []
        out.append(
            {
                "username": username,
                "forename": str(item.get("forename", item.get("firstname", "")) or "").strip(),
                "lastname": str(item.get("lastname", item.get("name", "")) or "").strip(),
                "roles": roles_list or ["user"],
                "enabled": bool(item.get("enabled", True)),
                "password_hash": str(item.get("password_hash", "") or ""),
            }
        )
    return out


def render(container: ui.element, _ctx: PageContext) -> None:
    with container.classes("w-full"):
        cfg = get_app_config()

        with ui.card().classes("w-full gap-3"):
            ui.label("User Management").classes("text-xl font-semibold")
            ui.label("Configure login validation and local users.").classes("text-sm text-gray-500")

            mode_select = ui.select(
                options=_AUTH_MODE_OPTIONS,
                value=str(cfg.auth.validation_mode or "local"),
                label="Validation mode",
            ).props("outlined")

            default_roles_input = ui.input(
                "Default roles (comma separated)",
                value=", ".join(cfg.auth.default_roles or ["user"]),
            ).classes("w-full")

            allow_legacy_switch = ui.switch(
                "Allow legacy fallback when users list is empty",
                value=bool(cfg.auth.allow_legacy_fallback),
            )

            with ui.row().classes("w-full gap-3"):
                rest_endpoint_input = ui.input(
                    "REST endpoint name for auth",
                    value=str(cfg.auth.rest_endpoint_name or ""),
                ).classes("flex-1")
                itac_connection_input = ui.input(
                    "iTAC connection name for auth",
                    value=str(cfg.auth.itac_connection_name or ""),
                ).classes("flex-1")
            ui.label(
                "In iTAC modes, authentication uses only the configured iTAC connection name above."
            ).classes("text-xs text-gray-500")

            with ui.row().classes("w-full gap-3"):
                rest_path_input = ui.input(
                    "REST login path (optional, e.g. /auth/login)",
                    value=str(cfg.auth.rest_login_path or ""),
                ).classes("flex-1")
                rest_method_select = ui.select(
                    options=["POST", "GET", "PUT", "PATCH"],
                    value=str(cfg.auth.rest_method or "POST").upper(),
                    label="REST method",
                ).props("outlined").classes("w-40")
                rest_timeout_input = ui.input(
                    "REST timeout (s)",
                    value=str(cfg.auth.rest_timeout_s or 8.0),
                ).classes("w-40")

            with ui.row().classes("w-full gap-3"):
                rest_success_field_input = ui.input(
                    "REST success field (optional, e.g. ok)",
                    value=str(cfg.auth.rest_success_field or ""),
                ).classes("flex-1")
                rest_user_field_input = ui.input(
                    "REST username field",
                    value=str(cfg.auth.rest_username_field or "username"),
                ).classes("w-52")
                rest_pass_field_input = ui.input(
                    "REST password field",
                    value=str(cfg.auth.rest_password_field or "password"),
                ).classes("w-52")

            def save_auth_settings() -> None:
                cfg_local = get_app_config()
                cfg_local.auth.validation_mode = str(mode_select.value or "local")
                cfg_local.auth.default_roles = _parse_roles(default_roles_input.value) or ["user"]
                cfg_local.auth.allow_legacy_fallback = bool(allow_legacy_switch.value)
                cfg_local.auth.rest_endpoint_name = str(rest_endpoint_input.value or "").strip()
                cfg_local.auth.itac_connection_name = str(itac_connection_input.value or "").strip()
                cfg_local.auth.rest_login_path = str(rest_path_input.value or "").strip()
                cfg_local.auth.rest_method = str(rest_method_select.value or "POST").upper().strip() or "POST"
                cfg_local.auth.rest_success_field = str(rest_success_field_input.value or "").strip()
                cfg_local.auth.rest_username_field = str(rest_user_field_input.value or "username").strip() or "username"
                cfg_local.auth.rest_password_field = str(rest_pass_field_input.value or "password").strip() or "password"
                try:
                    cfg_local.auth.rest_timeout_s = float(rest_timeout_input.value or 8.0)
                except Exception:
                    ui.notify("REST timeout must be a number.", type="negative")
                    return

                save_app_config(cfg_local)
                ui.notify("Authentication settings saved.", type="positive")

            with ui.row().classes("w-full justify-end"):
                ui.button("Save auth settings", on_click=save_auth_settings).props("color=primary")

        with ui.card().classes("w-full gap-3 mt-3"):
            ui.label("Local Users").classes("text-lg font-semibold")
            ui.label("Users are used for local authentication and role mapping.").classes("text-sm text-gray-500")

            @ui.refreshable
            def users_list() -> None:
                cfg_local = get_app_config()
                users = _users(cfg_local)

                if not users:
                    ui.label("No local users configured yet.").classes("text-sm text-gray-500")
                    return

                for idx, item in enumerate(users):
                    with ui.card().classes("w-full"):
                        with ui.row().classes("w-full items-center gap-3"):
                            username = ui.input("Username", value=item["username"]).classes("w-56")
                            forename = ui.input("Forename", value=item["forename"]).classes("w-44")
                            lastname = ui.input("Lastname", value=item["lastname"]).classes("w-44")
                            roles = ui.input("Roles", value=", ".join(item["roles"])).classes("flex-1")
                            enabled = ui.switch("Enabled", value=bool(item["enabled"]))
                            password = ui.input(
                                "New password (leave empty to keep current)",
                                password=True,
                                password_toggle_button=True,
                            ).classes("w-72")

                            def save_user(i=idx, u=username, fn=forename, ln=lastname, r=roles, e=enabled, p=password) -> None:
                                cfg_edit = get_app_config()
                                users_edit = _users(cfg_edit)
                                if i < 0 or i >= len(users_edit):
                                    ui.notify("User not found.", type="negative")
                                    return

                                new_username = str(u.value or "").strip()
                                if not new_username:
                                    ui.notify("Username is required.", type="negative")
                                    return

                                for j, other in enumerate(users_edit):
                                    if j == i:
                                        continue
                                    if str(other.get("username", "")).strip().lower() == new_username.lower():
                                        ui.notify("Username already exists.", type="negative")
                                        return

                                users_edit[i]["username"] = new_username
                                users_edit[i]["forename"] = str(fn.value or "").strip()
                                users_edit[i]["lastname"] = str(ln.value or "").strip()
                                users_edit[i]["roles"] = _parse_roles(r.value) or ["user"]
                                users_edit[i]["enabled"] = bool(e.value)

                                new_password = str(p.value or "")
                                if new_password:
                                    users_edit[i]["password_hash"] = hash_password(new_password)

                                cfg_edit.auth.users = users_edit
                                save_app_config(cfg_edit)
                                ui.notify("User updated.", type="positive")
                                users_list.refresh()

                            def delete_user(i=idx) -> None:
                                cfg_edit = get_app_config()
                                users_edit = _users(cfg_edit)
                                if i < 0 or i >= len(users_edit):
                                    ui.notify("User not found.", type="negative")
                                    return
                                users_edit.pop(i)
                                cfg_edit.auth.users = users_edit
                                save_app_config(cfg_edit)
                                ui.notify("User deleted.", type="positive")
                                users_list.refresh()

                            ui.button("Save", on_click=save_user).props("color=primary")
                            ui.button("Delete", on_click=delete_user).props("color=negative flat")

            def add_user() -> None:
                username = str(add_username.value or "").strip()
                if not username:
                    ui.notify("Username is required.", type="negative")
                    return

                cfg_local = get_app_config()
                users_local = _users(cfg_local)
                if any(str(u.get("username", "")).strip().lower() == username.lower() for u in users_local):
                    ui.notify("Username already exists.", type="negative")
                    return

                password_raw = str(add_password.value or "")
                user_entry = {
                    "username": username,
                    "forename": str(add_forename.value or "").strip(),
                    "lastname": str(add_lastname.value or "").strip(),
                    "roles": _parse_roles(add_roles.value) or ["user"],
                    "enabled": bool(add_enabled.value),
                    "password_hash": hash_password(password_raw) if password_raw else "",
                }
                users_local.append(user_entry)
                cfg_local.auth.users = users_local
                save_app_config(cfg_local)

                add_username.value = ""
                add_forename.value = ""
                add_lastname.value = ""
                add_roles.value = "user"
                add_password.value = ""
                add_enabled.value = True

                ui.notify("User added.", type="positive")
                users_list.refresh()

            with ui.row().classes("w-full items-end gap-3"):
                add_username = ui.input("Username").classes("w-56")
                add_forename = ui.input("Forename").classes("w-44")
                add_lastname = ui.input("Lastname").classes("w-44")
                add_roles = ui.input("Roles (comma separated)", value="user").classes("flex-1")
                add_password = ui.input("Password", password=True, password_toggle_button=True).classes("w-56")
                add_enabled = ui.switch("Enabled", value=True)
                ui.button("Add user", on_click=add_user).props("color=primary")

            users_list()
