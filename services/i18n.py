from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

from nicegui import app

I18N_PATH = "config/i18n/translations.json"
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


def _ensure_i18n_file() -> None:
    os.makedirs(os.path.dirname(I18N_PATH), exist_ok=True)
    if os.path.exists(I18N_PATH):
        return
    save_translations(_DEFAULT_TRANSLATIONS)


def load_translations() -> dict[str, dict[str, str]]:
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
    return language


def t(key: str, default: str | None = None, **kwargs: Any) -> str:
    translations = load_translations()
    lang = get_language()
    text = translations.get(key, {}).get(lang)
    if not text:
        text = translations.get(key, {}).get(DEFAULT_LANGUAGE)
    if not text:
        text = default if default is not None else key
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
    data = load_translations()
    merged = deepcopy(data)
    for key, values in _DEFAULT_TRANSLATIONS.items():
        merged.setdefault(key, {})
        for lang, text in values.items():
            merged[key].setdefault(lang, text)
    save_translations(merged)
