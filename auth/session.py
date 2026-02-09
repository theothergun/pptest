from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from nicegui import app


@dataclass(frozen=True)
class User:
    username: str
    roles: tuple[str, ...]  # e.g. ("admin",) or ("user",)


def get_user() -> Optional[User]:
    data = app.storage.user.get("user")
    if not data:
        return None
    return User(username=data["username"], roles=tuple(data.get("roles", ())))


def is_logged_in() -> bool:
    return get_user() is not None


def login(username: str, roles: tuple[str, ...]) -> None:
    app.storage.user["user"] = {"username": username, "roles": list(roles)}


def logout() -> None:
    app.storage.user.pop("user", None)


def has_role(role: str) -> bool:
    u = get_user()
    return bool(u and role in u.roles)
