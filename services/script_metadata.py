from __future__ import annotations

from pathlib import Path


def _title_from_path(path: str) -> str:
    name = Path(path).with_suffix("").name.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in name.split()) or "Automation Script"


def default_script_meta(path: str, *, title: str | None = None, description: str = "") -> dict[str, object]:
    script_path = Path(path)
    return {
        "title": title or _title_from_path(script_path.name),
        "description": description,
        "buttons": [
            {"id": "start", "label": "Start", "icon": "play_arrow", "color": "positive", "command": "script.start_chain"},
            {"id": "pause", "label": "Pause", "icon": "pause", "color": "warning", "command": "script.pause_chain"},
            {"id": "resume", "label": "Resume", "icon": "play_arrow", "color": "primary", "command": "script.resume_chain", "outline": True},
            {"id": "stop", "label": "Stop", "icon": "stop", "color": "negative", "command": "script.stop_chain"},
            {"id": "reload", "label": "Reload", "icon": "refresh", "color": "info", "command": "script.reload_script", "outline": True},
        ],
    }
