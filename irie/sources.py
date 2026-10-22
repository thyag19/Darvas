"""Data-source registry: what each source is, what we are allowed to do with it, and how often we try.

Access status is a *recorded decision*, not an inference from reachability:
  CLEARED        written permission or a published licence covers automated retrieval; evidence is required.
  USER_SUPPLIED  files placed in the inbox by the operator, who is responsible for their right to use them.
  NOT_CLEARED    no permission established. The scheduler logs an attempt and SKIPS it; nothing is fetched.
`display_cleared` (may the value be shown on the public site) is separate from `access` and defaults to False;
it needs its own evidence. A website being reachable grants neither.
"""
from __future__ import annotations

import datetime as dt
import enum
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

from .models import Source, SourceGrade


class Access(str, enum.Enum):
    CLEARED = "CLEARED"
    USER_SUPPLIED = "USER_SUPPLIED"
    NOT_CLEARED = "NOT_CLEARED"


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    name: str
    grade: SourceGrade
    kind: str                                  # 'file_inbox' | 'http'
    access: Access
    provides: Tuple[str, ...] = ()
    terms_url: str = ""
    terms_checked_on: Optional[dt.date] = None
    clearance_evidence: str = ""               # where the written permission/licence is recorded
    display_cleared: bool = False
    display_evidence: str = ""
    enabled: bool = True
    cadence_s: int = 3600                      # attempt every hour
    min_interval_s: float = 2.0                # minimum gap between requests to this source
    max_staleness_s: int = 7200                # FRESH only if the last good retrieval is younger than this
    max_attempts: int = 3
    notes: str = ""

    def to_source(self) -> Source:
        return Source(self.source_id, self.name, self.grade, self.terms_url, self.display_cleared, self.notes)

    @property
    def may_fetch(self) -> bool:
        return self.enabled and self.access in (Access.CLEARED, Access.USER_SUPPLIED)


class RegistryError(ValueError):
    pass


def validate(specs: Mapping[str, SourceSpec]) -> None:
    problems = []
    for s in specs.values():
        if s.access is Access.CLEARED and not (s.clearance_evidence.strip() and s.terms_checked_on):
            problems.append(f"{s.source_id}: CLEARED needs clearance_evidence and terms_checked_on")
        if s.display_cleared and not (s.display_evidence.strip() and s.terms_checked_on):
            problems.append(f"{s.source_id}: display_cleared needs display_evidence and terms_checked_on")
        if s.display_cleared and s.access is Access.NOT_CLEARED:
            problems.append(f"{s.source_id}: cannot display data from a NOT_CLEARED source")
        if s.kind == "http" and s.access is Access.USER_SUPPLIED:
            problems.append(f"{s.source_id}: USER_SUPPLIED is for file_inbox sources")
        if s.cadence_s < 60 or s.min_interval_s < 0 or s.max_attempts < 1:
            problems.append(f"{s.source_id}: invalid cadence/rate/attempt settings")
    if problems:
        raise RegistryError("; ".join(problems))


def parse_registry(obj: dict) -> Dict[str, SourceSpec]:
    specs: Dict[str, SourceSpec] = {}
    for r in obj["sources"]:
        sid = r["source_id"]
        if sid in specs:
            raise RegistryError(f"duplicate source_id {sid}")
        chk = r.get("terms_checked_on")
        specs[sid] = SourceSpec(
            sid, r["name"], SourceGrade(r["grade"]), r["kind"], Access(r["access"]), tuple(r.get("provides", ())),
            r.get("terms_url", ""), dt.date.fromisoformat(chk) if chk else None, r.get("clearance_evidence", ""),
            bool(r.get("display_cleared", False)), r.get("display_evidence", ""), bool(r.get("enabled", True)),
            int(r.get("cadence_s", 3600)), float(r.get("min_interval_s", 2.0)), int(r.get("max_staleness_s", 7200)),
            int(r.get("max_attempts", 3)), r.get("notes", ""))
    validate(specs)
    return specs


def load_registry(path) -> Dict[str, SourceSpec]:
    return parse_registry(json.loads(Path(path).read_text(encoding="utf-8")))
