from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import quote, unquote

from nicegui import ui

from layout.context import PageContext
from layout.page_scaffold import build_page


DOCS_DIR = Path(os.getcwd()) / "docs"
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _list_markdown_files() -> list[str]:
    if not DOCS_DIR.exists() or not DOCS_DIR.is_dir():
        return []

    files: list[str] = []
    for path in DOCS_DIR.rglob("*.md"):
        if path.is_file():
            files.append(path.relative_to(DOCS_DIR).as_posix())
    return sorted(files)


def _safe_doc_path(relative_path: str) -> Path | None:
    candidate = (DOCS_DIR / relative_path).resolve()
    try:
        candidate.relative_to(DOCS_DIR.resolve())
    except ValueError:
        return None
    return candidate


def _read_doc(relative_path: str) -> str:
    path = _safe_doc_path(relative_path)
    if path is None or not path.exists() or not path.is_file():
        return "Document not found."
    return path.read_text(encoding="utf-8", errors="replace")


def _resolve_relative_doc(base_doc: str, href: str) -> str | None:
    href_clean = (href or "").strip()
    if not href_clean:
        return None
    if href_clean.startswith(("http://", "https://", "mailto:", "#")):
        return None

    raw_target = href_clean.split("#", 1)[0].split("?", 1)[0]
    if not raw_target.lower().endswith(".md"):
        return None

    base_dir = Path(base_doc).parent
    target = (base_dir / raw_target).as_posix()
    safe = _safe_doc_path(target)
    if safe is None or not safe.exists() or not safe.is_file():
        return None
    return safe.relative_to(DOCS_DIR.resolve()).as_posix()


def _rewrite_local_links(markdown_text: str, base_doc: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2)
        resolved = _resolve_relative_doc(base_doc, href)
        if not resolved:
            return match.group(0)
        return f"[{label}](/?page=docs&doc={quote(resolved)})"

    return LINK_RE.sub(_replace, markdown_text)


def render(container: ui.element, ctx: PageContext) -> None:
    files = _list_markdown_files()
    requested_doc = ""
    try:
        requested_doc = unquote(str(ui.context.request.query_params.get("doc", ""))).strip()
    except Exception:
        requested_doc = ""

    selected_default = files[0] if files else ""
    if requested_doc and requested_doc in files:
        selected_default = requested_doc

    selected = {"path": selected_default}

    @ui.refreshable
    def docs_list() -> None:
        if not files:
            ui.label("No markdown files found in /docs.").classes("text-sm text-gray-500")
            return

        for relative_path in files:
            is_active = relative_path == selected["path"]
            color = "primary" if is_active else "grey-7"
            ui.button(
                relative_path,
                icon="description",
                on_click=lambda p=relative_path: _open_doc(p),
            ).props(f"flat no-caps align=left color={color}").classes("w-full justify-start")

    @ui.refreshable
    def doc_content() -> None:
        if not selected["path"]:
            ui.label("Select a document to view it.").classes("text-sm text-gray-500")
            return

        ui.label(selected["path"]).classes("text-sm text-gray-500")
        content = _rewrite_local_links(_read_doc(selected["path"]), selected["path"])
        ui.markdown(content).classes("w-full")

    def _open_doc(relative_path: str) -> None:
        selected["path"] = relative_path
        docs_list.refresh()
        doc_content.refresh()

    def build_content(_parent: ui.element) -> None:
        with ui.row().classes("w-full h-full min-h-0 gap-3"):
            with ui.card().classes("w-full sm:w-80 h-full min-h-0"):
                ui.label("Documents").classes("text-base font-semibold")
                with ui.column().classes("w-full flex-1 min-h-0 overflow-auto gap-1"):
                    docs_list()

            with ui.card().classes("w-full flex-1 h-full min-h-0"):
                with ui.column().classes("w-full h-full min-h-0 overflow-auto"):
                    doc_content()

    build_page(
        ctx,
        container,
        title="Documentation",
        content=build_content,
        show_action_bar=False,
        scroll_mode="none",
    )
