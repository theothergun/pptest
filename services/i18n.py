from __future__ import annotations

import inspect
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from nicegui import app

I18N_PATH = "config/i18n/translations.json"
MISSING_I18N_PATH = "config/i18n/missing_keys.json"
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "label": "English"},
    {"code": "de", "label": "Deutsch"},
    {"code": "zh", "label": "中文"},
    {"code": "mk", "label": "Македонски"},
    {"code": "es-MX", "label": "Español (México)"},
    {"code": "sk", "label": "Slovenčina"},
    {"code": "cs", "label": "Čeština"},
]
SUPPORTED_LANGUAGE_CODES = [entry["code"] for entry in SUPPORTED_LANGUAGES]

_DEFAULT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "app.title": {
        "en": "Shopfloor application",
        "de": "Shopfloor-Anwendung",
        "zh": "车间应用",
        "mk": "Апликација за производна линија",
        "es-MX": "Aplicación de piso de producción",
        "sk": "Aplikácia pre výrobnú halu",
        "cs": "Aplikace pro výrobní halu",
    },
    "header.toggle_nav": {
        "en": "Toggle Nav",
        "de": "Navigation umschalten",
        "zh": "切换导航",
        "mk": "Прикажи/скриј мени",
        "es-MX": "Alternar navegación",
        "sk": "Prepnúť navigáciu",
        "cs": "Přepnout navigaci",
    },
    "header.logout": {
        "en": "Logout",
        "de": "Abmelden",
        "zh": "退出登录",
        "mk": "Одјави се",
        "es-MX": "Cerrar sesión",
        "sk": "Odhlásiť sa",
        "cs": "Odhlásit se",
    },
    "settings.title": {
        "en": "Settings",
        "de": "Einstellungen",
        "zh": "设置",
        "mk": "Поставки",
        "es-MX": "Configuración",
        "sk": "Nastavenia",
        "cs": "Nastavení",
    },
    "settings.subtitle": {
        "en": "Manage application settings and worker configuration.",
        "de": "Anwendungseinstellungen und Worker-Konfiguration verwalten.",
        "zh": "管理应用设置和工作器配置。",
        "mk": "Управувај со поставки и конфигурација на работници.",
        "es-MX": "Administra la configuración de la aplicación y de workers.",
        "sk": "Spravujte nastavenia aplikácie a konfiguráciu workerov.",
        "cs": "Spravujte nastavení aplikace a konfiguraci workerů.",
    },
}

_i18n_lock = threading.RLock()


def _ensure_i18n_file() -> None:
    os.makedirs(os.path.dirname(I18N_PATH), exist_ok=True)
    if os.path.exists(I18N_PATH):
        return
    save_translations(_DEFAULT_TRANSLATIONS)


def _ensure_missing_i18n_file() -> None:
    os.makedirs(os.path.dirname(MISSING_I18N_PATH), exist_ok=True)
    if os.path.exists(MISSING_I18N_PATH):
        return
    with open(MISSING_I18N_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=2, ensure_ascii=False, sort_keys=True)


def _safe_load_missing_entries() -> dict[str, dict[str, Any]]:
    _ensure_missing_i18n_file()
    try:
        with open(MISSING_I18N_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        logger.exception(f"[_safe_load_missing_entries] - failed_read_missing_store - path={MISSING_I18N_PATH}")
        return {}


def _safe_write_missing_entries(entries: dict[str, dict[str, Any]]) -> None:
    tmp_path = f"{MISSING_I18N_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False, sort_keys=True)
    os.replace(tmp_path, MISSING_I18N_PATH)


def _guess_category(key: str) -> str:
    if ".tooltip" in key or key.startswith("tooltip"):
        return "tooltips"
    prefix = key.split(".", 1)[0]
    if prefix in {"errors", "status", "buttons", "ui"}:
        return prefix
    return "ui"


def _capture_missing_key(key: str, default_text: str, *, location: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _i18n_lock:
        entries = _safe_load_missing_entries()
        existing = entries.get(key, {})
        entries[key] = {
            "key": key,
            "default_text": default_text,
            "first_seen": existing.get("first_seen", now),
            "last_seen": now,
            "count": int(existing.get("count", 0)) + 1,
            "location": location,
            "category": existing.get("category", _guess_category(key)),
        }
        try:
            _safe_write_missing_entries(entries)
        except Exception:
            logger.exception(f"[_capture_missing_key] - failed_write_missing_store - key={key} location={location}")


def _get_callsite() -> str:
    frame = inspect.currentframe()
    if frame is None:
        return "unknown"
    caller = frame.f_back.f_back
    if caller is None:
        return "unknown"
    module = caller.f_globals.get("__name__", "unknown")
    fn_name = caller.f_code.co_name
    return f"{module}.{fn_name}"


def load_translations() -> dict[str, dict[str, str]]:
    with _i18n_lock:
        _ensure_i18n_file()
        with open(I18N_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    parsed: dict[str, dict[str, str]] = {}
    for key, values in raw.items():
        if not isinstance(values, dict):
            continue
        parsed[key] = {str(lang): str(text) for lang, text in values.items()}
    for key, values in _DEFAULT_TRANSLATIONS.items():
        parsed.setdefault(key, {}).update({k: v for k, v in values.items() if not parsed[key].get(k)})
    return parsed


def save_translations(translations: dict[str, dict[str, str]]) -> None:
    with _i18n_lock:
        os.makedirs(os.path.dirname(I18N_PATH), exist_ok=True)
        with open(I18N_PATH, "w", encoding="utf-8") as f:
            json.dump(translations, f, indent=2, ensure_ascii=False, sort_keys=True)


def get_language() -> str:
    lang = app.storage.user.get("language", DEFAULT_LANGUAGE)
    if lang not in SUPPORTED_LANGUAGE_CODES:
        return DEFAULT_LANGUAGE
    return lang


def set_language(language: str) -> str:
    language = language if language in SUPPORTED_LANGUAGE_CODES else DEFAULT_LANGUAGE
    app.storage.user["language"] = language
    logger.info(f"[set_language] - language_updated - language={language}")
    return language


def t(key: str, default: str | None = None, **kwargs: Any) -> str:
    translations = load_translations()
    lang = get_language()
    text = translations.get(key, {}).get(lang)
    if not text:
        text = translations.get(key, {}).get(DEFAULT_LANGUAGE)
    if not text:
        fallback = default if default is not None else key
        _capture_missing_key(key, fallback, location=_get_callsite())
        logger.debug(f"[t] - missing_translation - key={key} lang={lang} location={_get_callsite()}")
        text = fallback
    if kwargs:
        return text.format(**kwargs)
    return text


def new_phrase_template() -> dict[str, str]:
    return {code: "" for code in SUPPORTED_LANGUAGE_CODES}


def export_rows() -> list[dict[str, str]]:
    data = load_translations()
    rows: list[dict[str, str]] = []
    for key in sorted(data.keys()):
        row = {"key": key}
        for lang in SUPPORTED_LANGUAGE_CODES:
            row[lang] = data[key].get(lang, "")
        rows.append(row)
    return rows


def import_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        key = str(row.get("key", "")).strip()
        if not key:
            continue
        out[key] = {}
        for lang in SUPPORTED_LANGUAGE_CODES:
            value = str(row.get(lang, "")).strip()
            if value:
                out[key][lang] = value
    return out


def bootstrap_defaults() -> None:
    _ensure_i18n_file()
    _ensure_missing_i18n_file()
    data = load_translations()
    merged = deepcopy(data)
    for key, values in _DEFAULT_TRANSLATIONS.items():
        merged.setdefault(key, {})
        for lang, text in values.items():
            merged[key].setdefault(lang, text)
    save_translations(merged)
    logger.info(f"[bootstrap_defaults] - i18n_bootstrapped - keys={len(merged)}")
