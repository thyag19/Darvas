"""Load a seed bundle (the regression-fixture layout) through the validating importers.

Bundle files: instruments.csv, sources.csv, distributions.csv, snapshot.csv (+ optional meta.json).
Seed data is user-supplied and its provenance is unverified; sources default to display_cleared=False.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from .importing import ImportReport, import_distributions
from .models import (ETFCategory, Instrument, InstrumentType, LeverageDefinition, LeveragePoint, NavKind, NavPoint,
                     PricePoint, Source, SourceGrade)


@dataclass
class SeedBundle:
    as_of: dt.date
    instruments: Dict[str, Instrument]
    sources: Dict[str, Source]
    events: list
    prices: Dict[str, PricePoint]
    navs: Dict[str, NavPoint]
    leverage: Dict[str, LeveragePoint]
    report: ImportReport
    workbook_source_grade: Dict[str, str]


def _rows(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _dec(v):
    return Decimal(v) if v not in ("", None) else None


def _leverage_def(text: str) -> LeverageDefinition:
    t = text.lower()
    if t.startswith("sebi 'net borrowings"):
        return LeverageDefinition.SEBI_NET_BORROWINGS_RATIO
    if "net debt" in t and "/ ev" in t:
        return LeverageDefinition.NET_DEBT_TO_EV
    if "debt-ev" in t or "debt/ev" in t:
        return LeverageDefinition.DEBT_TO_EV
    return LeverageDefinition.OTHER


def load_bundle(directory) -> SeedBundle:
    d = Path(directory)
    meta = json.loads((d / "meta.json").read_text())
    as_of = dt.date.fromisoformat(meta["as_of"])
    instruments = {}
    for r in _rows(d / "instruments.csv"):
        instruments[r["key"]] = Instrument(
            r["key"], r["name"], InstrumentType(r["type"]),
            ETFCategory(r["etf_category"]) if r["etf_category"] else None,
            {"Y": True, "N": False}.get(r["distributes"]), r["isin"] or None,
            {k: r[c] for k, c in (("NSE", "nse_symbol"), ("BSE", "bse_symbol"), ("BSE_SCRIP", "bse_scrip")) if r[c]})
    sources = {r["source_id"]: Source(r["source_id"], r["name"], SourceGrade(r["grade"]), r["url"], False, r["comment"])
               for r in _rows(d / "sources.csv")}
    report = import_distributions((d / "distributions.csv").read_text(encoding="utf-8"), instruments,
                                  as_of=as_of, known_sources=sources)
    prices, navs, lev, wsg = {}, {}, {}, {}
    for r in _rows(d / "snapshot.csv"):
        k = r["key"]
        wsg[k] = r["workbook_source_grade"]
        if r["price"]:
            prices[k] = PricePoint(k, dt.date.fromisoformat(r["price_date"]), Decimal(r["price"]), r["price_venue"])
        if r["nav"]:
            # 'Verified' in the workbook = taken from the trust's official filing
            grade = SourceGrade.ISSUER if r["nav_status"] == "Verified" else SourceGrade.UNKNOWN
            navs[k] = NavPoint(k, dt.date.fromisoformat(r["nav_date"]), Decimal(r["nav"]), NavKind.FAIR_VALUE, grade)
        if r["gearing"]:
            grade = SourceGrade.ISSUER if r["gearing_status"] == "Verified" else SourceGrade.UNKNOWN
            lev[k] = LeveragePoint(k, dt.date.fromisoformat(r["gearing_date"]), Decimal(r["gearing"]),
                                   _leverage_def(r["gearing_definition"]), grade, "",
                                   r["gearing_definition"][:200])
    return SeedBundle(as_of, instruments, sources, report.accepted, prices, navs, lev, report, wsg)
