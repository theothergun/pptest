from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from dataclasses import asdict

from enum import IntEnum

from nicegui import ui


class ErrorWeight(IntEnum):
    NOT_SET = 0
    PASS = 1
    RECHECK = 2
    SCRAP = 3
    SAFE_LAUNCH = 4


class SerialNumState(IntEnum):
    NOT_SET = -1
    PASS = 0
    FAIL = 1
    SCRAP = 2
    IN_PROGRESS = 3
    NOT_ALLOWED = 5

@dataclass(frozen=True)
class GroupRow:
    group: str
    description: str


@dataclass(frozen=True)
class FailureRow:
    code: str
    description: str
    weight: ErrorWeight # 0 to 5
    group_code: str
    document_url: str
    # you can add more fields later (allowed_actions, doc_url, etc.)


class FailureCatalogue:
    """
    Holds catalogue data (groups/failures) and caches it.

    - load_once(): loads only the first time
    - refresh(): forces reload
    - failures_for_group(): query helper used by the UI
    """


    def __init__(self) -> None:
        self._loaded: bool = False
        self._groups: List[GroupRow] = []
        self._failures: List[FailureRow] = []
        self._failures_by_group: Dict[str, List[FailureRow]] = {}


    @property
    def loaded(self) -> bool:
        return self._loaded


    def load_once(self) -> None:
        """Load catalogue only once (no-op if already loaded)."""
        if self._loaded:
            return
        self._load(force=True)


    def refresh(self) -> None:
        """Force reload catalogue from the external source."""
        self._load(force=True)


    def _load(self, *, force: bool) -> None:
        """
        Replace this with your external source loading.


        For now, demo data.
        """
        # ---- DEMO DATA ----
        groups = [
        GroupRow("G01", "Cosmetics"),
        GroupRow("G02", "Soldering"),
        GroupRow("G03", "Labeling"),
        ]
        failures = [
        FailureRow("C101", "Scratch on cover", ErrorWeight.PASS, "G01", "https://research.google.com/pubs/archive/44678.pdf"),
        FailureRow("C102", "Dent on case", ErrorWeight.RECHECK, "G01","https://placebear.com/800/600"),
        FailureRow("S201", "Cold solder joint", ErrorWeight.SCRAP, "G02", "https://research.google.com/pubs/archive/44678.pdf"),
        FailureRow("S202", "Missing solder", ErrorWeight.NOT_SET, "G02","https://placebear.com/800/600"),
        FailureRow("L301", "Wrong label", ErrorWeight.SAFE_LAUNCH, "G03","https://research.google.com/pubs/archive/44678.pdf"),
        ]


        self._groups = groups
        self._failures = failures


        # pre-index for fast lookups
        by_group: Dict[str, List[FailureRow]] = {g.group: [] for g in groups}
        for f in failures:
            by_group.setdefault(f.group_code, []).append(f)
            self._failures_by_group = by_group

        self._loaded = True


    def groups(self) -> List[GroupRow]:
        """Return all groups (empty list if not loaded)."""
        return list(self._groups)


    def failures_for_group(self, group: Optional[str]) -> List[FailureRow]:
        """Return failures for a given group."""
        if not group:
            return []
        return list(self._failures_by_group.get(group, []))


    # UI Helpers
    def group_rows(self) -> list[dict]:
        return [asdict(g) for g in self.groups()]

    def failure_rows(self, group_key: str | None) -> list[dict]:
        return [asdict(f) for f in self.failures_for_group(group_key)]


