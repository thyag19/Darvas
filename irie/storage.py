"""Minimal SQLite repository over schema.sql. It exists to prove the schema round-trips the model and that
metrics computed from the database equal metrics computed from the files. The production database is expected
to be PostgreSQL (not yet exercised); this module is the only place that touches SQL.

Amounts are stored via str(Decimal) and read back with Decimal(str(value)); SQLite NUMERIC affinity may hold them
as REAL, which round-trips the 4-6 decimal-place amounts used here exactly (verified by test).
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Iterable, List

from .importing import ImportReport
from .models import (ComponentType, DistributionEvent, ETFCategory, Instrument, InstrumentType, PricePoint, Source,
                     SourceGrade, NavKind, NavPoint)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _d(v):
    return None if v is None else Decimal(str(v))


def save_sources(conn, sources: Iterable[Source]) -> None:
    conn.executemany("INSERT INTO source (source_id,name,grade,url,display_cleared,licence_note) VALUES (?,?,?,?,?,?)",
                     [(s.source_id, s.name, s.grade.value, s.url, int(s.display_cleared), s.comment) for s in sources])


def save_instruments(conn, instruments: Iterable[Instrument]) -> None:
    for i in instruments:
        conn.execute("INSERT INTO instrument (instrument_key,name,type,etf_category,distributes,isin) VALUES (?,?,?,?,?,?)",
                     (i.key, i.name, i.type.value, i.etf_category.value if i.etf_category else None,
                      None if i.distributes is None else int(i.distributes), i.isin))
        for exch, sym in i.symbols.items():
            if exch in ("NSE", "BSE"):
                conn.execute("INSERT INTO listing (instrument_key,exchange,symbol,scrip_code) VALUES (?,?,?,?)",
                             (i.key, exch, sym, i.symbols.get("BSE_SCRIP") if exch == "BSE" else None))


def save_import_run(conn, run_id: str, report: ImportReport, imported_at: str) -> None:
    conn.execute("INSERT INTO import_run VALUES (?,?,?,?,?,?,?)",
                 (run_id, report.kind, report.file_sha256, imported_at, report.rows_read, len(report.accepted),
                  report.rejected))
    conn.executemany("INSERT INTO import_issue VALUES (?,?,?,?,?,?)",
                     [(run_id, i.row, i.severity, i.code, i.message, None) for i in report.issues])


def save_events(conn, events: Iterable[DistributionEvent], run_id: str = None, review_ids=frozenset()) -> None:
    for e in events:
        conn.execute(
            "INSERT INTO distribution_event (event_id,instrument_key,ex_date,record_date,period_label,total_per_unit,"
            "include_flag,amount_grade,source_id,status_text,notes,review_status,run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.event_id, e.instrument_key, e.ex_date.isoformat(), e.record_date.isoformat() if e.record_date else None,
             e.period_label, None if e.total_per_unit is None else str(e.total_per_unit), int(e.include),
             e.amount_grade.value, e.source_id or None, e.status_text, e.notes,
             "NEEDS_REVIEW" if e.event_id in review_ids else "OK", run_id))
        conn.executemany("INSERT INTO distribution_component VALUES (?,?,?)",
                         [(e.event_id, c.value, str(v)) for c, v in e.components.items()])


def save_prices(conn, prices: Iterable[PricePoint]) -> None:
    conn.executemany("INSERT INTO price_eod (instrument_key,trade_date,venue,close,source_id) VALUES (?,?,?,?,?)",
                     [(p.instrument_key, p.date.isoformat(), p.venue, str(p.price), p.source_id or None) for p in prices])


def save_navs(conn, navs: Iterable[NavPoint]) -> None:
    conn.executemany("INSERT INTO nav (instrument_key,nav_date,kind,nav,grade,source_id) VALUES (?,?,?,?,?,?)",
                     [(n.instrument_key, n.nav_date.isoformat(), n.kind.value, str(n.nav), n.grade.value,
                       n.source_id or None) for n in navs])


def load_events(conn, instrument_key: str) -> List[DistributionEvent]:
    out = []
    rows = conn.execute("SELECT event_id,ex_date,record_date,period_label,total_per_unit,include_flag,amount_grade,"
                        "source_id,status_text,notes FROM distribution_event WHERE instrument_key=? ORDER BY ex_date,event_id",
                        (instrument_key,)).fetchall()
    for (eid, ex, rec, label, total, inc, grade, sid, st, notes) in rows:
        comps = {ComponentType(t): _d(a) for t, a in
                 conn.execute("SELECT component_type, amount FROM distribution_component WHERE event_id=?", (eid,))}
        out.append(DistributionEvent(eid, instrument_key, dt.date.fromisoformat(ex),
                                     dt.date.fromisoformat(rec) if rec else None, _d(total), comps, bool(inc),
                                     SourceGrade(grade), sid or "", label, st, notes))
    return out
