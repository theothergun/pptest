from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from starlette.requests import Request

from auth.session import is_logged_in
from services.app_config import get_app_config


PUBLIC_PATH_PREFIXES = (
    "/login",
    "/_nicegui",  # required for NiceGUI internal assets/websocket
    "/favicon",   # optional
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not get_app_config().auth.login_required:
            return await call_next(request)

        if path.startswith(PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        if not is_logged_in():
            return RedirectResponse("/login")

        return await call_next(request)
