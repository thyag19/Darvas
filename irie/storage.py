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


def save_events(conn, events: Iterable[DistributionEvent], run_id: str = None, review_ids=frozenset(),
                retrieved_at: str = None, document_id: str = None) -> int:
    inserted = 0
    for e in events:
        if conn.execute("SELECT 1 FROM distribution_event WHERE event_id=?", (e.event_id,)).fetchone():
            continue                      # idempotent: identical content from the same source is already stored
        inserted += 1
        conn.execute(
            "INSERT INTO distribution_event (event_id,instrument_key,ex_date,record_date,period_label,total_per_unit,"
            "include_flag,amount_grade,source_id,status_text,notes,review_status,run_id,retrieved_at,document_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.event_id, e.instrument_key, e.ex_date.isoformat(), e.record_date.isoformat() if e.record_date else None,
             e.period_label, None if e.total_per_unit is None else str(e.total_per_unit), int(e.include),
             e.amount_grade.value, e.source_id or None, e.status_text, e.notes,
             "NEEDS_REVIEW" if e.event_id in review_ids else "OK", run_id, retrieved_at, document_id))
        conn.executemany("INSERT INTO distribution_component VALUES (?,?,?)",
                         [(e.event_id, c.value, str(v)) for c, v in e.components.items()])
    return inserted


def save_prices(conn, prices: Iterable[PricePoint], retrieved_at: str = None, document_id: str = None) -> int:
    """Idempotent (same instrument/date/venue/source is ignored). Returns rows inserted."""
    n0 = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO price_eod (instrument_key,trade_date,venue,close,source_id,retrieved_at,document_id)"
                     " VALUES (?,?,?,?,?,?,?)",
                     [(p.instrument_key, p.date.isoformat(), p.venue, str(p.price), p.source_id, retrieved_at, document_id)
                      for p in prices])
    return conn.total_changes - n0


def save_navs(conn, navs: Iterable[NavPoint], retrieved_at: str = None, document_id: str = None) -> int:
    n0 = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO nav (instrument_key,nav_date,kind,nav,grade,source_id,retrieved_at,document_id)"
                     " VALUES (?,?,?,?,?,?,?,?)",
                     [(n.instrument_key, n.nav_date.isoformat(), n.kind.value, str(n.nav), n.grade.value, n.source_id,
                       retrieved_at, document_id) for n in navs])
    return conn.total_changes - n0


def save_leverage(conn, points, retrieved_at: str = None) -> int:
    n0 = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO leverage (instrument_key,as_of_date,definition,value,definition_note,grade,source_id,retrieved_at)"
                     " VALUES (?,?,?,?,?,?,?,?)",
                     [(p.instrument_key, p.date.isoformat(), p.definition.value, str(p.value), p.definition_note,
                       p.grade.value, p.source_id, retrieved_at) for p in points])
    return conn.total_changes - n0


def upsert_instruments(conn, instruments: Iterable[Instrument]) -> int:
    """Insert new instruments; existing keys are left untouched (a changed definition needs a deliberate migration)."""
    have = {r[0] for r in conn.execute("SELECT instrument_key FROM instrument")}
    new = [i for i in instruments if i.key not in have]
    save_instruments(conn, new)
    return len(new)


def sync_sources(conn, sources: Iterable[Source]) -> None:
    for s in sources:
        conn.execute("INSERT INTO source (source_id,name,grade,url,display_cleared,licence_note) VALUES (?,?,?,?,?,?) "
                     "ON CONFLICT(source_id) DO UPDATE SET name=excluded.name, grade=excluded.grade, url=excluded.url, "
                     "display_cleared=excluded.display_cleared, licence_note=excluded.licence_note",
                     (s.source_id, s.name, s.grade.value, s.url, int(s.display_cleared), s.comment))


def load_instruments(conn) -> dict:
    out = {}
    for key, name, typ, cat, dist, isin in conn.execute(
            "SELECT instrument_key,name,type,etf_category,distributes,isin FROM instrument ORDER BY instrument_key"):
        syms = {ex: sym for ex, sym in conn.execute("SELECT exchange,symbol FROM listing WHERE instrument_key=?", (key,))}
        out[key] = Instrument(key, name, InstrumentType(typ), ETFCategory(cat) if cat else None,
                              None if dist is None else bool(dist), isin, syms)
    return out


def load_sources(conn) -> dict:
    return {sid: Source(sid, name, SourceGrade(g), url, bool(dc), note) for sid, name, g, url, dc, note in
            conn.execute("SELECT source_id,name,grade,url,display_cleared,licence_note FROM source")}


def load_price_rows(conn, key: str):
    """[(PricePoint, retrieved_at)] for every source, oldest first."""
    return [(PricePoint(key, dt.date.fromisoformat(d), _d(c), v, s), r) for d, v, c, s, r in conn.execute(
        "SELECT trade_date,venue,close,source_id,retrieved_at FROM price_eod WHERE instrument_key=? ORDER BY trade_date", (key,))]


def load_nav_rows(conn, key: str):
    return [(NavPoint(key, dt.date.fromisoformat(d), _d(n), NavKind(k), SourceGrade(g), s), r) for d, k, n, g, s, r in
            conn.execute("SELECT nav_date,kind,nav,grade,source_id,retrieved_at FROM nav WHERE instrument_key=? ORDER BY nav_date", (key,))]


def load_leverage_rows(conn, key: str):
    from .models import LeverageDefinition, LeveragePoint
    return [(LeveragePoint(key, dt.date.fromisoformat(d), _d(v), LeverageDefinition(df), SourceGrade(g), s, note), r)
            for d, df, v, note, g, s, r in conn.execute(
                "SELECT as_of_date,definition,value,definition_note,grade,source_id,retrieved_at FROM leverage "
                "WHERE instrument_key=? ORDER BY as_of_date", (key,))]


def load_event_rows(conn, key: str):
    """[(DistributionEvent, retrieved_at)]."""
    out = []
    for ev in load_events(conn, key):
        r = conn.execute("SELECT retrieved_at FROM distribution_event WHERE event_id=?", (ev.event_id,)).fetchone()
        out.append((ev, r[0] if r else None))
    return out


def save_retrieval(conn, retrieval_id, source_id, started_at, finished_at, status, attempts=0, documents=0,
                   accepted=0, rejected=0, observed_through=None, error=None) -> None:
    conn.execute("INSERT INTO retrieval_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (retrieval_id, source_id, started_at, finished_at, status, attempts, documents, accepted, rejected,
                  observed_through.isoformat() if observed_through else None, error))


def last_attempt(conn, source_id):
    return conn.execute("SELECT started_at,status FROM retrieval_log WHERE source_id=? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                        (source_id,)).fetchone()


def last_success(conn, source_id):
    return conn.execute("SELECT finished_at,observed_through FROM retrieval_log WHERE source_id=? AND status IN "
                        "('OK','NO_NEW_DATA') ORDER BY finished_at DESC LIMIT 1", (source_id,)).fetchone()


def consecutive_failures(conn, source_id) -> int:
    n = 0
    for (st,) in conn.execute("SELECT status FROM retrieval_log WHERE source_id=? ORDER BY started_at DESC, rowid DESC", (source_id,)):
        if st == "ERROR":
            n += 1
        elif st.startswith("SKIPPED"):
            continue
        else:
            break
    return n


def store_discrepancies(conn, discs, detected_at: str) -> int:
    """Upsert OPEN discrepancies; resolved ones are never reopened or deleted (audit history)."""
    n0 = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO discrepancy (instrument_key,field,ref_date,source_a,value_a,source_b,value_b,abs_diff,detected_at)"
                     " VALUES (?,?,?,?,?,?,?,?,?)",
                     [(d.instrument_key, d.field, d.ref_date.isoformat(), d.source_a, str(d.value_a), d.source_b,
                       str(d.value_b), str(d.abs_diff), detected_at) for d in discs])
    return conn.total_changes - n0


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


def save_document(conn, document_id, source_id, url, retrieved_at, sha256, note="") -> bool:
    """Record a retrieved document. False if the same content (sha256) from this source is already recorded."""
    row = conn.execute("SELECT document_id,note FROM source_document WHERE source_id=? AND sha256=?", (source_id, sha256)).fetchone()
    if row and row[1] != "RETRY":
        return False
    if row:                      # flagged for reprocessing (e.g. it referenced instruments not yet known)
        conn.execute("UPDATE source_document SET note='' WHERE document_id=?", (row[0],))
        return True
    conn.execute("INSERT INTO source_document (document_id,source_id,url,retrieved_at,sha256,note) VALUES (?,?,?,?,?,?)",
                 (document_id, source_id, url, retrieved_at, sha256, note))
    return True


def mark_document_retry(conn, source_id, sha256) -> None:
    conn.execute("UPDATE source_document SET note='RETRY' WHERE source_id=? AND sha256=?", (source_id, sha256))
