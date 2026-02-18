from __future__ import annotations

from typing import Any

import requests
from loguru import logger

from auth.passwords import verify_password
from services.app_config import (
    WORKER_ITAC,
    WORKER_REST,
    get_app_config,
    get_worker_config,
)


VALIDATION_MODES = {
    "local",
    "rest_api",
    "itac",
    "local_or_rest_api",
    "local_or_itac",
}

ITAC_NO_USER_LOGGED_RV = -104
ITAC_USER_ALREADY_LOGGED_RV = -106


def _normalize_mode(raw: Any) -> str:
    value = str(raw or "local").strip().lower()
    return value if value in VALIDATION_MODES else "local"


def _normalize_roles(raw: Any, fallback: tuple[str, ...] = ("user",)) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return fallback
    out = tuple(str(r).strip() for r in raw if str(r).strip())
    return out or fallback


def _find_local_user(users: list[dict[str, Any]], username: str) -> dict[str, Any] | None:
    needle = str(username or "").strip().lower()
    for item in users:
        if not isinstance(item, dict):
            continue
        if str(item.get("username", "")).strip().lower() == needle:
            return item
    return None


def _validate_local(
    username: str,
    password: str,
    users: list[dict[str, Any]],
    allow_legacy_fallback: bool,
) -> tuple[bool, str, dict[str, str]]:
    user = _find_local_user(users, username)
    if user is not None:
        profile = {
            "forename": str(user.get("forename", user.get("firstname", "")) or "").strip(),
            "lastname": str(user.get("lastname", user.get("name", "")) or "").strip(),
        }
        if not bool(user.get("enabled", True)):
            return False, "User is disabled.", {}
        stored_hash = str(user.get("password_hash", "") or "")
        if not stored_hash:
            return False, "User has no password configured.", {}
        if verify_password(password, stored_hash):
            return True, "", profile
        return False, "Invalid username or password.", {}

    # Backward-compatible behavior from previous login implementation.
    if allow_legacy_fallback and not users:
        if bool(username):
            return True, "", {}
        return False, "Enter a username.", {}

    return False, "Invalid username or password.", {}


def _pick_endpoint(endpoints: list[dict[str, Any]], preferred_name: str, key_name: str = "name") -> dict[str, Any] | None:
    preferred_name = str(preferred_name or "").strip()
    if preferred_name:
        for ep in endpoints:
            if not isinstance(ep, dict):
                continue
            if str(ep.get(key_name, "")).strip() == preferred_name:
                return ep
    for ep in endpoints:
        if isinstance(ep, dict):
            return ep
    return None


def _join_url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip()
    p = str(path or "").strip()
    if not p:
        return base
    return f"{base.rstrip('/')}/{p.lstrip('/')}"


def _extract_roles_from_json(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    roles = payload.get("roles")
    if isinstance(roles, list):
        out = tuple(str(r).strip() for r in roles if str(r).strip())
        return out
    return ()


def _pick_non_empty_str(*values: Any) -> str:
    for v in values:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _extract_profile_names(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""

    result = payload.get("result")
    result_dict = result if isinstance(result, dict) else {}
    print(result_dict)
    # iTAC expected fields: firstname + name
    forename = _pick_non_empty_str(
        result_dict.get("forename"),
        result_dict.get("firstname"),
        result_dict.get("firstName"),
        payload.get("forename"),
        payload.get("firstname"),
        payload.get("firstName"),
    )
    lastname = _pick_non_empty_str(
        result_dict.get("lastname"),
        result_dict.get("name"),
        result_dict.get("lastName"),
        payload.get("lastname"),
        payload.get("name"),
        payload.get("lastName"),
    )
    return forename, lastname


def _validate_rest(username: str, password: str) -> tuple[bool, tuple[str, ...], str, dict[str, str]]:
    cfg = get_app_config()
    auth_cfg = cfg.auth

    rest_cfg = get_worker_config(cfg, WORKER_REST)
    endpoints = rest_cfg.get("endpoints", [])
    if not isinstance(endpoints, list):
        return False, (), "REST auth validation is configured but no REST endpoints exist.", {}

    endpoint = _pick_endpoint(endpoints, auth_cfg.rest_endpoint_name, "name")
    if endpoint is None:
        return False, (), "REST auth validation endpoint was not found.", {}

    base_url = str(endpoint.get("base_url", "")).strip()
    if not base_url:
        return False, (), "REST auth validation endpoint has no base_url.", {}

    method = str(auth_cfg.rest_method or "POST").strip().upper()
    url = _join_url(base_url, str(auth_cfg.rest_login_path or ""))
    verify_ssl = bool(endpoint.get("verify_ssl", True))
    endpoint_name = str(endpoint.get("name", "")).strip()

    timeout_s = float(auth_cfg.rest_timeout_s or endpoint.get("timeout_s", 8.0) or 8.0)

    headers: dict[str, str] = {}
    endpoint_headers = endpoint.get("headers", {})
    if isinstance(endpoint_headers, dict):
        headers.update({str(k): str(v) for k, v in endpoint_headers.items()})
    auth_headers = auth_cfg.rest_headers if isinstance(auth_cfg.rest_headers, dict) else {}
    headers.update({str(k): str(v) for k, v in auth_headers.items()})

    username_field = str(auth_cfg.rest_username_field or "username")
    password_field = str(auth_cfg.rest_password_field or "password")
    payload: dict[str, Any] = {}
    if isinstance(auth_cfg.rest_extra_payload, dict):
        payload.update(auth_cfg.rest_extra_payload)
    payload[username_field] = username
    payload[password_field] = password

    logger.info(
        "REST auth start: endpoint='{}' method='{}' url='{}' username='{}'",
        endpoint_name,
        method,
        url,
        username,
    )

    try:
        if method in ("GET", "HEAD"):
            resp = requests.request(
                method=method,
                url=url,
                params=payload,
                headers=headers,
                timeout=timeout_s,
                verify=verify_ssl,
            )
        else:
            resp = requests.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
                timeout=timeout_s,
                verify=verify_ssl,
            )
    except Exception as ex:
        logger.warning("REST auth validation failed: {}", ex)
        return False, (), f"REST auth validation request failed: {ex}", {}

    parsed_json: Any = None
    try:
        parsed_json = resp.json()
    except Exception:
        parsed_json = None

    ok_by_status = 200 <= int(resp.status_code) < 300
    success_field = str(auth_cfg.rest_success_field or "").strip()
    if success_field and isinstance(parsed_json, dict):
        is_ok = bool(parsed_json.get(success_field))
    elif isinstance(parsed_json, dict) and "ok" in parsed_json:
        is_ok = bool(parsed_json.get("ok"))
    elif isinstance(parsed_json, dict) and "success" in parsed_json:
        is_ok = bool(parsed_json.get("success"))
    else:
        is_ok = ok_by_status

    if not is_ok:
        if isinstance(parsed_json, dict):
            detail = (
                str(parsed_json.get("error", "")).strip()
                or str(parsed_json.get("message", "")).strip()
                or f"HTTP {resp.status_code}"
            )
        else:
            detail = f"HTTP {resp.status_code}"
        logger.warning(
            "REST auth rejected: endpoint='{}' username='{}' detail='{}'",
            endpoint_name,
            username,
            detail,
        )
        return False, (), f"REST auth validation rejected credentials: {detail}", {}

    logger.success("REST auth success: endpoint='{}' username='{}'", endpoint_name, username)
    forename, lastname = _extract_profile_names(parsed_json)
    return True, _extract_roles_from_json(parsed_json), "", {"forename": forename, "lastname": lastname}


def _itac_result(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    result = data.get("result")
    return result if isinstance(result, dict) else {}


def _itac_return_value(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None

    result = _itac_result(data)
    for key in ("return_value", "returnCode", "return_code", "resultCode", "result_code", "code"):
        if key in result:
            try:
                return int(result.get(key))
            except Exception:
                return None

    for key in ("returnCode", "return_code", "resultCode", "result_code", "code"):
        if key in data:
            try:
                return int(data.get(key))
            except Exception:
                return None

    return None


def _itac_session_context(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    ctx = data.get("sessionContext")
    if not isinstance(ctx, dict):
        ctx = _itac_result(data).get("sessionContext")
    if not isinstance(ctx, dict):
        return None

    session_id = str(ctx.get("sessionId") or ctx.get("session_id") or "").strip()
    if not session_id:
        return None

    pers_raw = ctx.get("persId") if "persId" in ctx else ctx.get("pers_id", 0)
    try:
        pers_id = int(pers_raw or 0)
    except Exception:
        pers_id = 0

    return {
        "sessionId": session_id,
        "persId": pers_id,
        "locale": str(ctx.get("locale") or ""),
    }


def _itac_registered_user(data: Any) -> str:
    result = _itac_result(data)
    return str(result.get("userName") or result.get("username") or "").strip()


def _itac_error_detail(data: Any, fallback: str = "") -> str:
    if not isinstance(data, dict):
        return fallback
    result = _itac_result(data)
    for src in (result, data):
        if not isinstance(src, dict):
            continue
        detail = (
            str(src.get("error", "")).strip()
            or str(src.get("message", "")).strip()
            or str(src.get("errorMessage", "")).strip()
        )
        if detail:
            return detail
    return fallback


def _itac_post_action(endpoint: dict[str, Any], function_name: str, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
    base_url = str(endpoint.get("base_url", "")).strip()
    if not base_url:
        return {}, "iTAC endpoint has no base_url."

    timeout_s = float(endpoint.get("timeout_s", 10.0) or 10.0)
    verify_ssl = bool(endpoint.get("verify_ssl", True))
    url = _join_url(base_url, function_name)

    try:
        resp = requests.post(
            url=url,
            json=body,
            timeout=timeout_s,
            verify=verify_ssl,
            headers={"Content-Type": "application/json"},
        )
    except Exception as ex:
        logger.warning("iTAC action '{}' failed: {}", function_name, ex)
        return {}, f"iTAC {function_name} request failed: {ex}"

    try:
        parsed: Any = resp.json()
    except Exception:
        parsed = {"raw": resp.text}

    parsed_dict = parsed if isinstance(parsed, dict) else {"data": parsed}
    if not (200 <= int(resp.status_code) < 300):
        detail = _itac_error_detail(parsed_dict, f"HTTP {resp.status_code}")
        return parsed_dict, f"iTAC {function_name} failed: {detail}"

    return parsed_dict, ""


def _validate_itac(username: str, password: str) -> tuple[bool, tuple[str, ...], str, dict[str, str]]:
    cfg = get_app_config()
    auth_cfg = cfg.auth

    itac_cfg = get_worker_config(cfg, WORKER_ITAC)
    endpoints = itac_cfg.get("endpoints", [])
    if not isinstance(endpoints, list):
        return False, (), "iTAC auth validation is configured but no iTAC endpoints exist.", {}

    endpoint = _pick_endpoint(endpoints, auth_cfg.itac_connection_name, "name")
    if endpoint is None:
        return False, (), "iTAC auth validation endpoint was not found.", {}
    endpoint_name = str(endpoint.get("name", "")).strip()

    station_number = str(endpoint.get("station_number", "") or "").strip()
    if not station_number:
        return False, (), "iTAC auth validation endpoint has no station_number.", {}

    client = str(endpoint.get("client", "01") or "01").strip() or "01"
    logger.info(
        "iTAC auth start: endpoint='{}' station='{}' username='{}' client='{}'",
        endpoint_name,
        station_number,
        username,
        client,
    )

    login_response, login_err = _itac_post_action(
        endpoint,
        "regLogin",
        {
            "sessionValidationStruct": {
                "stationNumber": station_number,
                "stationPassword": str(endpoint.get("station_password", "") or ""),
                "user": str(endpoint.get("user", "") or ""),
                "password": str(endpoint.get("password", "") or ""),
                "client": client,
                "registrationType": str(endpoint.get("registration_type", "S") or "S"),
                "systemIdentifier": str(endpoint.get("system_identifier", "nicegui") or "nicegui"),
            }
        },
    )
    if login_err:
        logger.warning(
            "iTAC auth regLogin failed: endpoint='{}' station='{}' user='{}' detail='{}'",
            endpoint_name,
            station_number,
            username,
            login_err,
        )
        return False, (), login_err, {}

    session_ctx = _itac_session_context(login_response)
    if not isinstance(session_ctx, dict):
        logger.warning(
            "iTAC auth regLogin missing session context: endpoint='{}' station='{}'",
            endpoint_name,
            station_number,
        )
        return False, (), "iTAC regLogin did not return a valid session context.", {}

    def with_session(payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        body["sessionContext"] = dict(session_ctx)
        return body

    get_user_res, get_user_err = _itac_post_action(
        endpoint,
        "regGetRegisteredUser",
        with_session({"stationNumber": station_number}),
    )
    if get_user_err:
        logger.warning(
            "iTAC auth regGetRegisteredUser failed: endpoint='{}' station='{}' detail='{}'",
            endpoint_name,
            station_number,
            get_user_err,
        )
        return False, (), get_user_err, {}

    get_user_rv = _itac_return_value(get_user_res)
    if get_user_rv == ITAC_NO_USER_LOGGED_RV:
        registered_user = ""
        logger.info(
            "iTAC auth regGetRegisteredUser: endpoint='{}' station='{}' return_value={} => no user logged in, skip unregister",
            endpoint_name,
            station_number,
            get_user_rv,
        )
    elif get_user_rv != 0:
        detail = _itac_error_detail(get_user_res, f"return_value={get_user_rv}")
        logger.warning(
            "iTAC auth regGetRegisteredUser returned error: endpoint='{}' station='{}' detail='{}'",
            endpoint_name,
            station_number,
            detail,
        )
        return False, (), f"iTAC regGetRegisteredUser failed: {detail}", {}
    else:
        registered_user = _itac_registered_user(get_user_res)
        logger.info(
            "iTAC auth current registered user: endpoint='{}' station='{}' user='{}'",
            endpoint_name,
            station_number,
            registered_user,
        )

    if registered_user and registered_user.lower() == username.lower():
        logger.info(
            "iTAC auth same user already registered: endpoint='{}' station='{}' user='{}' -> skip unregister",
            endpoint_name,
            station_number,
            registered_user,
        )
    elif registered_user:
        unregister_res, unregister_err = _itac_post_action(
            endpoint,
            "regUnregisterUser",
            with_session(
                {
                    "stationNumber": station_number,
                    "userName": registered_user,
                    "password": registered_user,
                    "client": client,
                }
            ),
        )
        if unregister_err:
            logger.warning(
                "iTAC auth regUnregisterUser failed: endpoint='{}' station='{}' user='{}' detail='{}'",
                endpoint_name,
                station_number,
                registered_user,
                unregister_err,
            )
            return False, (), unregister_err, {}
        unregister_rv = _itac_return_value(unregister_res)
        if unregister_rv != 0:
            detail = _itac_error_detail(unregister_res, f"return_value={unregister_rv}")
            logger.warning(
                "iTAC auth regUnregisterUser returned error: endpoint='{}' station='{}' user='{}' detail='{}'",
                endpoint_name,
                station_number,
                registered_user,
                detail,
            )
            return False, (), f"iTAC regUnregisterUser failed: {detail}", {}
        logger.info(
            "iTAC auth regUnregisterUser success: endpoint='{}' station='{}' user='{}'",
            endpoint_name,
            station_number,
            registered_user,
        )

    register_res, register_err = _itac_post_action(
        endpoint,
        "regRegisterUser",
        with_session(
            {
                "stationNumber": station_number,
                "userName": username,
                "password": password,
                "client": client,
            }
        ),
    )
    if register_err:
        logger.warning(
            "iTAC auth regRegisterUser failed: endpoint='{}' station='{}' user='{}' detail='{}'",
            endpoint_name,
            station_number,
            username,
            register_err,
        )
        return False, (), register_err, {}

    register_rv = _itac_return_value(register_res)
    if register_rv not in (0, ITAC_USER_ALREADY_LOGGED_RV):
        detail = _itac_error_detail(register_res, f"return_value={register_rv}")
        logger.warning(
            "iTAC auth regRegisterUser returned error: endpoint='{}' station='{}' user='{}' detail='{}'",
            endpoint_name,
            station_number,
            username,
            detail,
        )
        return False, (), f"iTAC login rejected credentials: {detail}", {}
    if register_rv == ITAC_USER_ALREADY_LOGGED_RV:
        logger.info(
            "iTAC auth regRegisterUser: endpoint='{}' station='{}' user='{}' return_value={} => already logged in (treated as success)",
            endpoint_name,
            station_number,
            username,
            register_rv,
        )

    logger.success(
        "iTAC auth success: endpoint='{}' station='{}' username='{}'",
        endpoint_name,
        station_number,
        username,
    )

    # Request profile fields from iTAC by registering once more.
    profile_res = register_res
    profile_res2, profile_err2 = _itac_post_action(
        endpoint,
        "regRegisterUser",
        with_session(
            {
                "stationNumber": station_number,
                "userName": username,
                "password": password,
                "client": client,
            }
        ),
    )
    if profile_err2:
        logger.warning(
            "iTAC auth second regRegisterUser failed: endpoint='{}' station='{}' user='{}' detail='{}'",
            endpoint_name,
            station_number,
            username,
            profile_err2,
        )
    else:
        profile_rv2 = _itac_return_value(profile_res2)
        if profile_rv2 in (0, ITAC_USER_ALREADY_LOGGED_RV):
            profile_res = profile_res2
        else:
            logger.warning(
                "iTAC auth second regRegisterUser returned error: endpoint='{}' station='{}' user='{}' return_value={}",
                endpoint_name,
                station_number,
                username,
                profile_rv2,
            )

    # Retrieve profile fields from regGetRegisteredUser after login.
    profile_get_res, profile_get_err = _itac_post_action(
        endpoint,
        "regGetRegisteredUser",
        with_session({"stationNumber": station_number}),
    )
    if profile_get_err:
        logger.warning(
            "iTAC auth post-login regGetRegisteredUser failed: endpoint='{}' station='{}' user='{}' detail='{}'",
            endpoint_name,
            station_number,
            username,
            profile_get_err,
        )
    else:
        profile_get_rv = _itac_return_value(profile_get_res)
        if profile_get_rv == 0:
            profile_res = profile_get_res
        else:
            logger.warning(
                "iTAC auth post-login regGetRegisteredUser returned error: endpoint='{}' station='{}' user='{}' return_value={}",
                endpoint_name,
                station_number,
                username,
                profile_get_rv,
            )

    forename, lastname = _extract_profile_names(profile_res)
    return True, _extract_roles_from_json(profile_res), "", {"forename": forename, "lastname": lastname}


def unregister_itac_user(username: str) -> tuple[bool, str]:
    user = str(username or "").strip()
    if not user:
        return True, "no_username"

    cfg = get_app_config()
    auth_cfg = cfg.auth
    mode = _normalize_mode(auth_cfg.validation_mode)
    if mode not in ("itac", "local_or_itac"):
        return True, "itac_logout_not_required_for_mode"

    itac_cfg = get_worker_config(cfg, WORKER_ITAC)
    endpoints = itac_cfg.get("endpoints", [])
    if not isinstance(endpoints, list):
        return False, "itac_endpoints_missing"

    endpoint = _pick_endpoint(endpoints, auth_cfg.itac_connection_name, "name")
    if endpoint is None:
        return False, "itac_endpoint_not_found"

    endpoint_name = str(endpoint.get("name", "")).strip()
    station_number = str(endpoint.get("station_number", "") or "").strip()
    if not station_number:
        return False, "itac_station_number_missing"

    client = str(endpoint.get("client", "01") or "01").strip() or "01"
    logger.info(
        "iTAC logout start: endpoint='{}' station='{}' username='{}'",
        endpoint_name,
        station_number,
        user,
    )

    login_response, login_err = _itac_post_action(
        endpoint,
        "regLogin",
        {
            "sessionValidationStruct": {
                "stationNumber": station_number,
                "stationPassword": str(endpoint.get("station_password", "") or ""),
                "user": str(endpoint.get("user", "") or ""),
                "password": str(endpoint.get("password", "") or ""),
                "client": client,
                "registrationType": str(endpoint.get("registration_type", "S") or "S"),
                "systemIdentifier": str(endpoint.get("system_identifier", "nicegui") or "nicegui"),
            }
        },
    )
    if login_err:
        logger.warning(
            "iTAC logout regLogin failed: endpoint='{}' station='{}' detail='{}'",
            endpoint_name,
            station_number,
            login_err,
        )
        return False, login_err

    session_ctx = _itac_session_context(login_response)
    if not isinstance(session_ctx, dict):
        return False, "itac_logout_session_context_missing"

    def with_session(payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        body["sessionContext"] = dict(session_ctx)
        return body

    get_user_res, get_user_err = _itac_post_action(
        endpoint,
        "regGetRegisteredUser",
        with_session({"stationNumber": station_number}),
    )
    if get_user_err:
        return False, get_user_err

    get_user_rv = _itac_return_value(get_user_res)
    if get_user_rv == ITAC_NO_USER_LOGGED_RV:
        logger.info("iTAC logout: no registered user on station='{}'", station_number)
        return True, "no_user_logged_in"
    if get_user_rv != 0:
        return False, f"itac_get_registered_user_failed_{get_user_rv}"

    registered_user = _itac_registered_user(get_user_res)
    if not registered_user:
        return True, "empty_registered_user"

    unregister_res, unregister_err = _itac_post_action(
        endpoint,
        "regUnregisterUser",
        with_session(
            {
                "stationNumber": station_number,
                "userName": registered_user,
                "password": registered_user,
                "client": client,
            }
        ),
    )
    if unregister_err:
        return False, unregister_err

    unregister_rv = _itac_return_value(unregister_res)
    if unregister_rv != 0:
        return False, f"itac_unregister_failed_{unregister_rv}"

    logger.success(
        "iTAC logout success: endpoint='{}' station='{}' unregistered='{}' requested_by='{}'",
        endpoint_name,
        station_number,
        registered_user,
        user,
    )
    return True, ""


def authenticate_user(username: str, password: str) -> tuple[bool, tuple[str, ...], str, dict[str, str]]:
    username = str(username or "").strip()
    password = str(password or "")
    if not username:
        return False, (), "Enter a username.", {}
    if not password:
        return False, (), "Enter a password.", {}

    cfg = get_app_config()
    auth_cfg = cfg.auth

    users = auth_cfg.users if isinstance(auth_cfg.users, list) else []
    local_user = _find_local_user(users, username)
    default_roles = _normalize_roles(auth_cfg.default_roles, ("user",))

    if local_user is not None and not bool(local_user.get("enabled", True)):
        return False, (), "User is disabled.", {}

    mode = _normalize_mode(auth_cfg.validation_mode)
    logger.info("Auth attempt: username='{}' mode='{}'", username, mode)

    def _roles_for_success(external_roles: tuple[str, ...] = ()) -> tuple[str, ...]:
        if local_user is not None:
            return _normalize_roles(local_user.get("roles"), default_roles)
        if external_roles:
            return external_roles
        # Legacy fallback from old login behavior if local users are not configured.
        if bool(auth_cfg.allow_legacy_fallback) and not users:
            return ("admin",) if username.lower() == "admin" else ("user",)
        return default_roles

    def _profile_for_success(external_profile: dict[str, str] | None = None) -> dict[str, str]:
        if local_user is not None:
            return {
                "forename": str(local_user.get("forename", local_user.get("firstname", "")) or "").strip(),
                "lastname": str(local_user.get("lastname", local_user.get("name", "")) or "").strip(),
            }
        if isinstance(external_profile, dict):
            return {
                "forename": str(external_profile.get("forename", "") or "").strip(),
                "lastname": str(external_profile.get("lastname", "") or "").strip(),
            }
        return {"forename": "", "lastname": ""}

    if mode in ("local", "local_or_rest_api", "local_or_itac"):
        ok_local, err_local, local_profile = _validate_local(
            username=username,
            password=password,
            users=users,
            allow_legacy_fallback=bool(auth_cfg.allow_legacy_fallback),
        )
        if ok_local:
            logger.success("Auth local success: username='{}'", username)
            return True, _roles_for_success(), "", _profile_for_success(local_profile)
        if mode == "local":
            logger.warning("Auth local failed: username='{}' reason='{}'", username, err_local)
            return False, (), err_local, {}

    if mode in ("rest_api", "local_or_rest_api"):
        ok_rest, rest_roles, err_rest, rest_profile = _validate_rest(username, password)
        if ok_rest:
            logger.success("Auth REST success: username='{}'", username)
            return True, _roles_for_success(rest_roles), "", _profile_for_success(rest_profile)
        if mode == "rest_api":
            logger.warning("Auth REST failed: username='{}' reason='{}'", username, err_rest)
            return False, (), err_rest, {}

    if mode in ("itac", "local_or_itac"):
        ok_itac, itac_roles, err_itac, itac_profile = _validate_itac(username, password)
        if ok_itac:
            logger.success("Auth iTAC success: username='{}'", username)
            return True, _roles_for_success(itac_roles), "", _profile_for_success(itac_profile)
        if mode == "itac":
            logger.warning("Auth iTAC failed: username='{}' reason='{}'", username, err_itac)
            return False, (), err_itac, {}

    logger.warning("Auth failed: username='{}' mode='{}'", username, mode)
    return False, (), "Invalid username or password.", {}
