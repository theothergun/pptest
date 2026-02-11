from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_FILE = ROOT / "config" / "i18n" / "translations.json"

LANG_CODES = ["en", "de", "zh", "mk", "es-MX", "sk", "cs"]
TARGET_UI_CALLS = {
    "label",
    "button",
    "tab",
    "notify",
    "input",
    "textarea",
    "markdown",
}
TARGET_KEYWORD_ARGS = {"label", "placeholder", "title"}


def normalize_key(text: str) -> str:
    key = text.strip().lower()
    key = key.replace("/", " ")
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return f"auto.{key or 'text'}"


def extract_from_file(path: Path) -> tuple[set[str], dict[str, str]]:
    texts: set[str] = set()
    keyed: dict[str, str] = {}
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # ui.<call>("...")
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "ui":
                if node.func.attr in TARGET_UI_CALLS and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        value = first.value.strip()
                        if value:
                            texts.add(value)

                for kw in node.keywords:
                    if kw.arg in TARGET_KEYWORD_ARGS and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        value = kw.value.value.strip()
                        if value:
                            texts.add(value)

                        # t("key", "fallback")
            if isinstance(node.func, ast.Name) and node.func.id == "t" and len(node.args) >= 2:
                first = node.args[0]
                second = node.args[1]
                if isinstance(second, ast.Constant) and isinstance(second.value, str):
                    value = second.value.strip()
                    if value:
                        texts.add(value)
                        if isinstance(first, ast.Constant) and isinstance(first.value, str):
                            keyed[first.value] = value

    return texts, keyed


def extract_all_texts() -> tuple[list[str], dict[str, str]]:
    texts: set[str] = set()
    keyed_map: dict[str, str] = {}
    for py_file in ROOT.rglob("*.py"):
        if any(part.startswith(".") for part in py_file.parts):
            continue
        if "venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        try:
            file_texts, file_keyed = extract_from_file(py_file)
            texts.update(file_texts)
            keyed_map.update(file_keyed)
        except SyntaxError:
            continue
    return sorted(texts), keyed_map


def build_translation_payload(texts: list[str], keyed_map: dict[str, str]) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    used_keys: set[str] = set()

    for key, text in sorted(keyed_map.items()):
        payload[key] = {lang: text for lang in LANG_CODES}

    for text in texts:
        base = normalize_key(text)
        key = base
        idx = 2
        while key in used_keys or key in payload:
            key = f"{base}_{idx}"
            idx += 1
        used_keys.add(key)

        payload[key] = {lang: text for lang in LANG_CODES}
        payload[key]["en"] = text

    return payload


def main() -> None:
    texts, keyed_map = extract_all_texts()
    payload = build_translation_payload(texts, keyed_map)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {len(payload)} translation keys -> {OUT_FILE}")


if __name__ == "__main__":
    main()
