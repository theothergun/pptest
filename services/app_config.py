from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from loguru import logger

# --------------------------------------------------------------------------------------
# Multiple config sets
# --------------------------------------------------------------------------------------

# If you set APP_CONFIG_PATH, it overrides everything (useful for production/testing).
ENV_CONFIG_PATH = os.environ.get("APP_CONFIG_PATH")

CONFIG_SETS_DIR = "config/sets"
ACTIVE_SET_FILE = "config/active_set.json"

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _ensure_config_dirs() -> None:
    os.makedirs(CONFIG_SETS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(ACTIVE_SET_FILE), exist_ok=True)


def _safe_set_name(name: str) -> str:
    name = (name or "").strip()
    name = _SAFE_NAME_RE.sub("-", name).strip("-")
    return name or "default"


def _set_path(set_name: str) -> str:
    _ensure_config_dirs()
    return os.path.join(CONFIG_SETS_DIR, f"{_safe_set_name(set_name)}.json")


def list_config_sets() -> list[str]:
    """Returns list of available config set names (without .json)."""
    _ensure_config_dirs()
    out: list[str] = []
    for fn in os.listdir(CONFIG_SETS_DIR):
        if fn.endswith(".json"):
            out.append(fn[:-5])
    return sorted(out)


def get_active_set_name() -> str:
    """Returns the currently active set name, creating a default pointer if missing."""
    _ensure_config_dirs()

    if not os.path.exists(ACTIVE_SET_FILE):
        set_active_set_name("default")

    try:
        with open(ACTIVE_SET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = _safe_set_name(data.get("active", "default"))
    except Exception:
        name = "default"

    # Ensure the file exists; if not, create empty config file.
    path = _set_path(name)
    if not os.path.exists(path):
        # create minimal config (defaults get written by load_app_config anyway)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

    return name


def set_active_set_name(name: str) -> None:
    """Persist the active set pointer."""
    _ensure_config_dirs()
    name = _safe_set_name(name)
    with open(ACTIVE_SET_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": name}, f, indent=2)


def create_config_set(name: str, *, copy_from: str | None = None) -> str:
    """
    Create a new config set JSON file.
    If copy_from is provided, copies that set's JSON content.
    """
    _ensure_config_dirs()
    name = _safe_set_name(name)
    dst = _set_path(name)
    if os.path.exists(dst):
        raise ValueError(f"Config set '{name}' already exists")

    data: dict[str, Any] = {}
    if copy_from:
        src = _set_path(copy_from)
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data = raw

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    return name


def get_config_path() -> str:
    """
    Canonical config path resolver.

    Priority:
      1) APP_CONFIG_PATH env override (absolute or relative)
      2) active set file: config/sets/<active>.json
    """
    if ENV_CONFIG_PATH:
        return ENV_CONFIG_PATH
    return _set_path(get_active_set_name())


# Keep this name for backward compatibility with your codebase,
# but now it is *resolved dynamically*.
DEFAULT_CONFIG_PATH = get_config_path()


# --------------------------------------------------------------------------------------
# Your existing config dataclasses (only small adjustments)
# --------------------------------------------------------------------------------------

# ------------------------------------------------------------------ Worker Names (authoritative)

WORKER_SCRIPT = "script_worker"
WORKER_TCP = "tcp_client"
WORKER_REST = "rest_api"
WORKER_TWINCAT = "twincat"
WORKER_ITAC = "itac"
WORKER_COM_DEVICE  = "com_device"
WORKER_OPCUA = "opcua"


# ------------------------------------------------------------------ Config models

@dataclass
class PersistenceConfig:
    backend: str = "json"
    # IMPORTANT: do not freeze to DEFAULT_CONFIG_PATH at import time; resolve when needed
    json_path: str = field(default_factory=get_config_path)
    external_db: dict[str, Any] = field(default_factory=lambda: {"enabled": False, "dsn": ""})


@dataclass
class AuthConfig:
    login_required: bool = True


@dataclass
class NavigationConfig:
    visible_routes: list[str] = field(
        default_factory=lambda: [
            "home", "errors", "reports", "settings",
            "settings_summary", "route_settings",
            "tcp_settings", "scripts", "example"
        ]
    )
    main_route: str = "home"
    hide_nav_on_startup: bool = False
    dark_mode: bool = False
    custom_routes: list[dict[str, Any]] = field(default_factory=list)
    route_roles: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class UiConfig:
    navigation: NavigationConfig = field(default_factory=NavigationConfig)

@dataclass
class ComDeviceEntry:
    device_id: str
    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
    timeout_s: float = 0.2
    write_timeout_s: float = 0.5

    mode: str = "line"		# "line" or "raw"
    delimiter: str = "\\n"	# keep escaped form in JSON, decode in helper
    encoding: str = "utf-8"

    read_chunk_size: int = 256
    max_line_len: int = 4096

    reconnect_min_s: float = 0.5
    reconnect_max_s: float = 5.0

@dataclass
class TcpClientEntry:
    client_id: str
    host: str
    port: int
    connect: bool = True
    mode: str = "line"
    delimiter: str = "\\n"
    encoding: str = "utf-8"
    auto_reconnect: bool = True
    reconnect_min_s: float = 1.0
    reconnect_max_s: float = 10.0
    keepalive: bool = True
    tcp_nodelay: bool = True


@dataclass
class RestApiEndpoint:
    name: str
    base_url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 10.0
    verify_ssl: bool = True


@dataclass
class TwincatEndpoint:
    plc_ams_net_id: str
    plc_ip: str
    ads_port: int
    client_id: str
    subscriptions: list[dict[str, Any]] = field(default_factory=list)
    default_trans_mode: str = "server_cycle"
    default_cycle_ms: int = 200
    default_string_len: int = 80


@dataclass
class ItacEndpoint:
    name: str
    base_url: str
    station_number: str
    client: str = "01"
    registration_type: str = "S"
    system_identifier: str = "nicegui"
    station_password: str = ""
    user: str = ""
    password: str = ""
    timeout_s: float = 10.0
    verify_ssl: bool = True
    auto_login: bool = True
    force_locale: str = ""

@dataclass
class OpcUaEndpoint:
    name: str
    server_url: str
    security_policy: str = "None"
    security_mode: str = "None"
    username: str = ""
    password: str = ""
    timeout_s: float = 5.0
    auto_connect: bool = False
    nodes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProxyConfig:
    enabled: bool = False
    http: str = ""
    https: str = ""
    no_proxy: str = ""  # comma separated: "localhost,127.0.0.1,10.1.2.

@dataclass
class WorkersConfig:
    # These names must match WORKER_* constants
    enabled_workers: list[str] = field(
        default_factory=lambda: [WORKER_SCRIPT, WORKER_TCP, WORKER_REST]
    )
    configs: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    auth: AuthConfig = field(default_factory=AuthConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    workers: WorkersConfig = field(default_factory=WorkersConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)


_APP_CONFIG: AppConfig | None = None


def clear_app_config_cache() -> None:
    """Clear cached config (use when switching sets)."""
    global _APP_CONFIG
    _APP_CONFIG = None


def set_active_set(name: str) -> None:
    """
    Switch active config set and clear cached AppConfig.
    Your UI can call this, then reload the page.
    """
    set_active_set_name(name)
    clear_app_config_cache()


def get_app_config() -> AppConfig:
    global _APP_CONFIG
    if _APP_CONFIG is None:
        _APP_CONFIG = load_app_config()
    return _APP_CONFIG


def load_app_config(path: str | None = None) -> AppConfig:
    config_path = path or get_config_path()
    log = logger.bind(component="AppConfig", path=config_path)

    if not os.path.exists(config_path):
        log.warning("Config not found. Writing defaults.")
        cfg = AppConfig()
        save_app_config(cfg, config_path)
        return cfg

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return _from_dict(raw)


def save_app_config(cfg: AppConfig, path: str | None = None) -> None:
    config_path = path or get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(_to_dict(cfg), f, indent=2, sort_keys=True)

    # Keep cache in sync
    _APP_CONFIG = cfg


def _to_dict(cfg: AppConfig) -> dict[str, Any]:
    return asdict(cfg)


# ------------------------------------------------------------------ Parsing

def _from_dict(data: dict[str, Any]) -> AppConfig:
    auth = AuthConfig(**data.get("auth", {}))

    nav_data = data.get("ui", {}).get("navigation", {})
    navigation = NavigationConfig(
        visible_routes=nav_data.get("visible_routes", NavigationConfig().visible_routes),
        main_route=nav_data.get("main_route", NavigationConfig().main_route),
        hide_nav_on_startup=bool(nav_data.get("hide_nav_on_startup", False)),
        dark_mode=bool(nav_data.get("dark_mode", False)),
        custom_routes=nav_data.get("custom_routes", []),
        route_roles=nav_data.get("route_roles", {}),
    )
    ui_cfg = UiConfig(navigation=navigation)

    workers_raw = data.get("workers", {})
    configs = workers_raw.get("configs")
    if configs is None:
        configs = {k: v for k, v in workers_raw.items() if k != "enabled_workers"}

    workers_cfg = WorkersConfig(
        enabled_workers=workers_raw.get("enabled_workers", WorkersConfig().enabled_workers),
        configs=configs,
    )

    # ensure persistence.json_path always points to the active file unless explicitly set
    persistence = PersistenceConfig(**data.get("persistence", {}))
    if not persistence.json_path:
        persistence.json_path = get_config_path()

    proxy = ProxyConfig(**data.get("proxy", {}))

    return AppConfig(auth=auth, ui=ui_cfg, workers=workers_cfg, persistence=persistence, proxy=proxy)


# ------------------------------------------------------------------ Helpers

def get_worker_config(cfg: AppConfig, worker_name: str) -> dict[str, Any]:
    config = cfg.workers.configs.get(worker_name)
    return config if isinstance(config, dict) else {}


def get_tcp_client_entries(cfg: AppConfig) -> list[TcpClientEntry]:
    raw_clients = get_worker_config(cfg, WORKER_TCP).get("clients", [])
    return [TcpClientEntry(**e) for e in raw_clients if isinstance(e, dict)]


def get_script_auto_start_chains(cfg: AppConfig) -> list[dict[str, Any]]:
    raw_chains = get_worker_config(cfg, WORKER_SCRIPT).get("auto_start_chains", [])
    return [e for e in raw_chains if isinstance(e, dict)]


def get_rest_api_endpoints(cfg: AppConfig) -> list[RestApiEndpoint]:
    raw = get_worker_config(cfg, WORKER_REST).get("endpoints", [])
    return [RestApiEndpoint(**e) for e in raw if isinstance(e, dict)]



def get_itac_endpoints(cfg: AppConfig) -> list[ItacEndpoint]:
    raw = get_worker_config(cfg, WORKER_ITAC).get("endpoints", [])
    return [ItacEndpoint(**e) for e in raw if isinstance(e, dict)]

def get_twincat_plc_endpoints(cfg: AppConfig) -> list[TwincatEndpoint]:
    raw = get_worker_config(cfg, WORKER_TWINCAT).get("plc_endpoints", [])
    entries: list[TwincatEndpoint] = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        entries.append(
            TwincatEndpoint(
                plc_ams_net_id=e["plc_ams_net_id"],
                plc_ip=e["plc_ip"],
                ads_port=e["ads_port"],
                client_id=e["client_id"],
                subscriptions=e.get("subscriptions", []),
            )
        )
    return entries

def get_com_device_entries(cfg: AppConfig) -> list[ComDeviceEntry]:
    raw_devices = get_worker_config(cfg, WORKER_COM_DEVICE).get("devices", [])
    entries: list[ComDeviceEntry] = []
    for e in raw_devices:
        if not isinstance(e, dict):
            continue
        if not e.get("device_id") and e.get("id"):
            e = dict(e)
            e["device_id"] = e.get("id")
        if "delimiter" in e:
            e = dict(e)
            e["delimiter"] = _decode_escaped(e.get("delimiter", "\\n"))
        entries.append(ComDeviceEntry(**e))
    return entries


def get_opcua_endpoints(cfg: AppConfig) -> list[OpcUaEndpoint]:
    raw = get_worker_config(cfg, WORKER_OPCUA).get("endpoints", [])
    return [OpcUaEndpoint(**e) for e in raw if isinstance(e, dict)]


def _decode_escaped(s: str) -> str:
    # keep it simple: your configs use \n and \r most of the time
    if s is None:
        return ""
    s = str(s)
    return s.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")
