"""Metric result type. A metric is a value OR an explicit reason it is unavailable; never a silent zero."""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from .models import Source


class Status(str, enum.Enum):
    OK = "OK"                          # value computed
    PARTIAL = "PARTIAL"                # inputs only partly available; value withheld
    UNAVAILABLE = "UNAVAILABLE"        # cannot be computed from the data supplied
    NOT_APPLICABLE = "NOT_APPLICABLE"  # metric is not defined for this instrument type/category


# Flags that stop a figure being treated as publishable. Other flags are caveats shown to the reader.
BLOCKING_FLAGS = frozenset({
    "UNVERIFIED_SOURCE", "PRICE_STALE", "AMOUNT_UNAVAILABLE_IN_WINDOW", "COMPONENTS_DO_NOT_RECONCILE",
    "NAV_UNVERIFIED", "NAV_STALE", "LEVERAGE_UNVERIFIED",
})


@dataclass(frozen=True)
class MetricResult:
    name: str
    status: Status
    as_of: dt.date
    value: Optional[Decimal] = None
    unit: str = ""
    reasons: tuple = ()
    flags: tuple = ()
    source_ids: tuple = ()
    inputs: tuple = ()  # (label, str(value)) pairs for traceability

    @property
    def ok(self) -> bool:
        return self.status is Status.OK

    def with_flags(self, *flags: str) -> "MetricResult":
        merged = tuple(dict.fromkeys(self.flags + tuple(flags)))
        return MetricResult(self.name, self.status, self.as_of, self.value, self.unit, self.reasons, merged,
                            self.source_ids, self.inputs)


def ok(name, as_of, value, unit="", flags=(), source_ids=(), inputs=()) -> MetricResult:
    return MetricResult(name, Status.OK, as_of, value, unit, (), tuple(dict.fromkeys(flags)),
                        tuple(sorted(set(source_ids))), tuple(inputs))


def withheld(name, as_of, status, reasons, unit="", flags=(), source_ids=(), inputs=()) -> MetricResult:
    assert status is not Status.OK
    return MetricResult(name, status, as_of, None, unit, tuple(reasons), tuple(dict.fromkeys(flags)),
                        tuple(sorted(set(source_ids))), tuple(inputs))


def publish_decision(result: MetricResult, sources: Mapping[str, Source]) -> tuple:
    """(publishable, reasons). Policy hook only: it enforces the data-quality and licence gates, and is
    NOT evidence that any licence exists. Every source defaults to display_cleared=False."""
    reasons = []
    if not result.ok:
        reasons.append(f"status {result.status.value}")
    reasons += [f"blocking flag {f}" for f in result.flags if f in BLOCKING_FLAGS]
    for sid in result.source_ids:
        src = sources.get(sid)
        if src is None:
            reasons.append(f"unknown source {sid}")
        elif not src.display_cleared:
            reasons.append(f"source {sid} not cleared for display")
    return (not reasons, reasons)
