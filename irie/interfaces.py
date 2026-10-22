"""Future integration contracts (no implementations in M1; nothing here touches the network).

Scheduled acquisition (M2+) must produce RawDocument objects; parsing and validation then reuse irie.importing,
so live and file-based data pass through identical checks. An Acquirer is only to be written for a source whose
access and display licence have been cleared (see docs/M1_TECHNICAL.md, "Gates").
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .models import Source
from .registry import Snapshot
from .result import MetricResult


@dataclass(frozen=True)
class RawDocument:
    source_id: str
    url: str
    retrieved_at: dt.datetime        # timezone-aware UTC; supplied by the acquirer, never read inside the engine
    sha256: str
    content: bytes


class Acquirer(Protocol):
    source: Source

    def fetch(self, as_of: dt.date) -> Sequence[RawDocument]:
        """Return raw documents for as_of. Must honour the source's licence terms and rate limits."""


class SnapshotExporter(Protocol):
    def export(self, snapshots: Sequence[Snapshot], results: Mapping[str, Mapping[str, MetricResult]],
               sources: Mapping[str, Source]) -> Mapping[str, bytes]:
        """Static-site JSON: only results for which irie.result.publish_decision is (True, [])."""
