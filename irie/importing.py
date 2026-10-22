"""Validating CSV importers. Every input row ends in exactly one place: accepted, accepted-with-review, or
rejected, and every decision is reported with a code and the original row. Nothing is silently repaired,
defaulted to zero, or dropped.

Severity: REJECT (row not imported), REVIEW (imported, flagged ambiguous), INFO (imported, noted).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Mapping, Optional

from .calc.distributions import TOLERANCE
from .models import (ALLOWED_COMPONENTS, ComponentType, DistributionEvent, Instrument, NavKind, NavPoint,
                     PricePoint, SourceGrade, VERIFIED_GRADES)

REJECT, REVIEW, INFO = "REJECT", "REVIEW", "INFO"
COMPONENT_COLUMNS = {"interest": ComponentType.INTEREST, "dividend": ComponentType.DIVIDEND,
                     "rental": ComponentType.RENTAL, "other_income": ComponentType.OTHER_INCOME,
                     "capital_repayment": ComponentType.CAPITAL_REPAYMENT}
RECORD_GAP_REVIEW_DAYS = 3


@dataclass(frozen=True)
class Issue:
    row: int
    severity: str
    code: str
    message: str


@dataclass
class ImportReport:
    kind: str
    file_sha256: str
    accepted: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    rows_read: int = 0
    rejected_rows: set = field(default_factory=set)
    raw: dict = field(default_factory=dict)

    def add(self, row: int, severity: str, code: str, msg: str) -> None:
        self.issues.append(Issue(row, severity, code, msg))
        if severity == REJECT:
            self.rejected_rows.add(row)

    @property
    def rejected(self) -> int:
        return len(self.rejected_rows)

    def count(self, severity: str) -> int:
        return len({i.row for i in self.issues if i.severity == severity})

    def codes(self, severity: Optional[str] = None) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for i in self.issues:
            if severity is None or i.severity == severity:
                out[i.code] = out.get(i.code, 0) + 1
        return dict(sorted(out.items()))

    def summary(self) -> dict:
        return {"kind": self.kind, "file_sha256": self.file_sha256, "rows_read": self.rows_read,
                "accepted": len(self.accepted), "rejected": self.rejected,
                "accepted_needing_review": len({i.row for i in self.issues if i.severity == REVIEW} - self.rejected_rows),
                "codes": self.codes()}

    def to_json(self) -> str:
        return json.dumps({"summary": self.summary(),
                           "issues": [{"row": i.row, "severity": i.severity, "code": i.code, "message": i.message,
                                       "input": self.raw.get(i.row)} for i in self.issues]},
                          indent=2, sort_keys=True, default=str)


def _read(text: str, required: Iterable[str], kind: str):
    rep = ImportReport(kind, hashlib.sha256(text.encode("utf-8")).hexdigest())
    rd = csv.DictReader(io.StringIO(text))
    missing = [c for c in required if c not in (rd.fieldnames or [])]
    if missing:
        raise ValueError(f"{kind}: missing required column(s) {missing}; found {rd.fieldnames}")
    return rep, rd


def _date(v: str) -> dt.date:
    return dt.date.fromisoformat(v.strip())  # strict ISO yyyy-mm-dd; ambiguous dd/mm forms are rejected


def _dec(v: Optional[str]) -> Optional[Decimal]:
    """None for blank. Raises ValueError for anything that is not a finite decimal."""
    if v is None or v.strip() == "":
        return None
    try:
        d = Decimal(v.strip())
    except InvalidOperation:
        raise ValueError(f"not a number: {v!r}")
    if not d.is_finite():
        raise ValueError(f"not finite: {v!r}")
    return d


def import_distributions(text: str, instruments: Mapping[str, Instrument], *, as_of: Optional[dt.date] = None,
                         known_sources: Optional[Mapping[str, object]] = None,
                         tolerance: Decimal = TOLERANCE) -> ImportReport:
    rep, rd = _read(text, ["instrument_key", "ex_date", "total_per_unit"], "distributions")
    seen_exact: Dict[tuple, int] = {}
    by_key_date: Dict[tuple, List[tuple]] = {}
    pending: List[tuple] = []  # (row, DistributionEvent)
    for lineno, row in enumerate(rd, start=2):
        rep.rows_read += 1
        rep.raw[lineno] = dict(row)
        key = (row.get("instrument_key") or "").strip()
        if not key:
            rep.add(lineno, REJECT, "MISSING_INSTRUMENT_KEY", "instrument_key is blank"); continue
        inst = instruments.get(key)
        if inst is None:
            rep.add(lineno, REJECT, "UNKNOWN_INSTRUMENT", f"{key!r} is not in the instrument list"); continue
        try:
            if not (row.get("ex_date") or "").strip():
                rep.add(lineno, REJECT, "MISSING_EX_DATE", "ex_date is blank"); continue
            ex = _date(row["ex_date"])
            rec = _date(row["record_date"]) if (row.get("record_date") or "").strip() else None
        except ValueError as e:
            rep.add(lineno, REJECT, "BAD_DATE", f"{e} (dates must be ISO yyyy-mm-dd)"); continue
        try:
            total = _dec(row.get("total_per_unit"))
            comps = {}
            for col, ctype in COMPONENT_COLUMNS.items():
                v = _dec(row.get(col))
                if v is not None:
                    comps[ctype] = v
        except ValueError as e:
            rep.add(lineno, REJECT, "BAD_NUMBER", str(e)); continue
        if (total is not None and total < 0) or any(v < 0 for v in comps.values()):
            rep.add(lineno, REJECT, "NEGATIVE_AMOUNT", "amounts must be >= 0"); continue
        bad_c = set(comps) - ALLOWED_COMPONENTS[inst.type]
        if bad_c:
            rep.add(lineno, REJECT, "COMPONENT_NOT_ALLOWED",
                    f"{sorted(c.value for c in bad_c)} not valid for {inst.type.value}; no split is invented"); continue
        inc_raw = (row.get("include") or "Y").strip().upper()
        if inc_raw not in ("Y", "N"):
            rep.add(lineno, REJECT, "BAD_INCLUDE_FLAG", f"include must be Y or N, got {inc_raw!r}"); continue
        grade_raw = (row.get("amount_grade") or "UNKNOWN").strip().upper()
        try:
            grade = SourceGrade(grade_raw)
        except ValueError:
            rep.add(lineno, REJECT, "BAD_GRADE", f"unknown amount_grade {grade_raw!r}"); continue
        sid = (row.get("source_id") or "").strip()
        include = inc_raw == "Y"

        sig = (key, ex, rec, total, tuple(sorted((c.value, v) for c, v in comps.items())))
        if sig in seen_exact:
            rep.add(lineno, REJECT, "DUPLICATE_RECORD", f"identical to row {seen_exact[sig]}"); continue
        seen_exact[sig] = lineno

        if total is None and include:
            include = False
            rep.add(lineno, REVIEW, "INCLUDE_WITHOUT_AMOUNT",
                    "include=Y but no amount: kept as amount-unavailable and excluded from calculations")
        if total is None and comps:
            rep.add(lineno, REVIEW, "COMPONENTS_WITHOUT_TOTAL", "components given without a total; cannot reconcile")
        if total is not None and comps and abs(sum(comps.values()) - total) > tolerance:
            rep.add(lineno, REVIEW, "COMPONENTS_DO_NOT_RECONCILE",
                    f"components sum {sum(comps.values())} vs total {total} (tolerance {tolerance})")
        if rec is not None and rec < ex:
            rep.add(lineno, REVIEW, "RECORD_BEFORE_EX_DATE", f"record {rec} precedes ex {ex}")
        elif rec is not None and (rec - ex).days > RECORD_GAP_REVIEW_DAYS:
            rep.add(lineno, REVIEW, "RECORD_DATE_GAP", f"record date is {(rec - ex).days} days after ex-date (derived ex-date?)")
        if as_of is not None and ex > as_of:
            rep.add(lineno, REVIEW, "EX_DATE_AFTER_AS_OF", f"ex-date {ex} is after as_of {as_of}; excluded from windows")
        if sid and known_sources is not None and sid not in known_sources:
            rep.add(lineno, REVIEW, "UNKNOWN_SOURCE_ID", f"source {sid!r} is not in the source register")
        if total is not None and grade not in VERIFIED_GRADES:
            rep.add(lineno, INFO, "UNVERIFIED_AMOUNT_SOURCE", f"amount grade {grade.value}: flagged UNVERIFIED_SOURCE in metrics")
        h = hashlib.sha1(repr(sig).encode()).hexdigest()[:10]
        ev = DistributionEvent(f"{key}:{ex.isoformat()}:{h}", key, ex, rec, total, comps, include, grade, sid,
                               (row.get("period_label") or "").strip(), (row.get("status_text") or "").strip(),
                               (row.get("notes") or "").strip())
        pending.append((lineno, ev))
        by_key_date.setdefault((key, ex), []).append((lineno, ev))

    for (key, ex), items in by_key_date.items():
        if len(items) > 1:
            for lineno, _ in items:
                rep.add(lineno, REVIEW, "SAME_EX_DATE_MULTIPLE_RECORDS",
                        f"{len(items)} records for {key} on {ex}: two components of one distribution, or a duplicate?")
    rep.accepted = [ev for _, ev in pending]
    return rep


def import_prices(text: str, instruments: Mapping[str, Instrument], *, as_of: Optional[dt.date] = None) -> ImportReport:
    rep, rd = _read(text, ["instrument_key", "date", "price"], "prices")
    seen: Dict[tuple, tuple] = {}
    for lineno, row in enumerate(rd, start=2):
        rep.rows_read += 1
        rep.raw[lineno] = dict(row)
        key = (row.get("instrument_key") or "").strip()
        if key not in instruments:
            rep.add(lineno, REJECT, "UNKNOWN_INSTRUMENT", f"{key!r} is not in the instrument list"); continue
        try:
            d = _date(row["date"])
        except ValueError as e:
            rep.add(lineno, REJECT, "BAD_DATE", f"{e} (dates must be ISO yyyy-mm-dd)"); continue
        try:
            px = _dec(row["price"])
        except ValueError as e:
            rep.add(lineno, REJECT, "BAD_NUMBER", str(e)); continue
        if px is None or px <= 0:
            rep.add(lineno, REJECT, "PRICE_NOT_POSITIVE", "price must be a positive number (blank is not zero)"); continue
        if as_of is not None and d > as_of:
            rep.add(lineno, REJECT, "DATE_AFTER_AS_OF", f"{d} is after as_of {as_of}"); continue
        venue = (row.get("venue") or "").strip()
        k = (key, d, venue)
        if k in seen:
            code = "DUPLICATE_RECORD" if seen[k] == px else "CONFLICTING_DUPLICATE"
            rep.add(lineno, REJECT, code, f"{key} {d} {venue}: already {seen[k]}"); continue
        seen[k] = px
        rep.accepted.append(PricePoint(key, d, px, venue, (row.get("source_id") or "").strip()))
    return rep


def import_navs(text: str, instruments: Mapping[str, Instrument], *, as_of: Optional[dt.date] = None) -> ImportReport:
    rep, rd = _read(text, ["instrument_key", "nav_date", "nav"], "navs")
    seen: Dict[tuple, Decimal] = {}
    for lineno, row in enumerate(rd, start=2):
        rep.rows_read += 1
        rep.raw[lineno] = dict(row)
        key = (row.get("instrument_key") or "").strip()
        if key not in instruments:
            rep.add(lineno, REJECT, "UNKNOWN_INSTRUMENT", f"{key!r} is not in the instrument list"); continue
        try:
            d = _date(row["nav_date"]); nav = _dec(row["nav"])
            kind = NavKind((row.get("kind") or NavKind.FAIR_VALUE.value).strip().upper())
            grade = SourceGrade((row.get("grade") or "UNKNOWN").strip().upper())
        except ValueError as e:
            rep.add(lineno, REJECT, "BAD_VALUE", str(e)); continue
        if nav is None or nav <= 0:
            rep.add(lineno, REJECT, "NAV_NOT_POSITIVE", "NAV must be positive (blank is not zero)"); continue
        if as_of is not None and d > as_of:
            rep.add(lineno, REJECT, "DATE_AFTER_AS_OF", f"{d} is after as_of {as_of}"); continue
        k = (key, d, kind)
        if k in seen:
            rep.add(lineno, REJECT, "DUPLICATE_RECORD" if seen[k] == nav else "CONFLICTING_DUPLICATE",
                    f"{key} {d} {kind.value}: already {seen[k]}"); continue
        seen[k] = nav
        rep.accepted.append(NavPoint(key, d, nav, kind, grade, (row.get("source_id") or "").strip()))
    return rep
