"""Hourly acquisition cycle: registry-driven, rate-limited, retried, fully logged. No network code lives here.

A Fetcher turns a source into RawDocuments; this module decides whether the source may be fetched at all, throttles
and retries it, validates what comes back through irie.importing, stores observations with BOTH timestamps
(retrieved_at = when we fetched; the row's own date = when it was observed), records every attempt in retrieval_log
(including skipped ones, so staleness is auditable), and detects cross-source discrepancies. One failing source never
stops the cycle. Only NOT_CLEARED sources are skipped by design; nothing is ever fetched from them.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import random
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from . import discrepancy as dsc
from . import freshness as fr
from . import importing as imp
from . import storage as st
from .interfaces import RawDocument
from .models import Instrument, SourceGrade
from .sources import SourceSpec

KINDS = ("instruments", "distributions", "prices", "navs", "leverage")


class FetchError(Exception):
    """Transient failure (timeout, 5xx, 429): retried with backoff."""


class PermanentFetchError(Exception):
    """Do not retry (403, 404, 451, permission withdrawn): the operator must act."""


class Fetcher(Protocol):
    def fetch(self, spec: SourceSpec, as_of: dt.date) -> Sequence[RawDocument]: ...


class RateLimiter:
    """Enforces a minimum gap between calls to one source."""

    def __init__(self, min_interval_s: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval_s, self._clock, self._sleep, self._last = min_interval_s, clock, sleep, None

    def wait(self) -> None:
        if self._last is not None:
            gap = self._clock() - self._last
            if gap < self.min_interval_s:
                self._sleep(self.min_interval_s - gap)
        self._last = self._clock()


def with_retries(fn: Callable[[], object], attempts: int, base_delay: float = 1.0, max_delay: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, rng: Callable[[], float] = random.random):
    """Exponential backoff with jitter. Returns (result, attempts_used). PermanentFetchError is never retried."""
    last: Optional[Exception] = None
    for n in range(1, attempts + 1):
        try:
            return fn(), n
        except PermanentFetchError:
            raise
        except FetchError as e:
            last = e
            if n < attempts:
                sleep(min(max_delay, base_delay * (2 ** (n - 1))) * (0.5 + rng() / 2))
    raise FetchError(f"gave up after {attempts} attempts: {last}")


class FileInboxFetcher:
    """Reads operator-supplied CSVs from <root>/<source_id>/<kind>_*.csv. Content-hash dedupe happens downstream."""

    def __init__(self, root, clock: Callable[[], dt.datetime]):
        self.root, self.clock = Path(root), clock

    def fetch(self, spec: SourceSpec, as_of: dt.date) -> Sequence[RawDocument]:
        d = self.root / spec.source_id
        docs = []
        for p in sorted(d.glob("*.csv")) if d.is_dir() else []:
            b = p.read_bytes()
            docs.append(RawDocument(spec.source_id, p.name, self.clock(), hashlib.sha256(b).hexdigest(), b))
        return docs


@dataclass
class SourceOutcome:
    source_id: str
    status: str
    attempts: int = 0
    documents: int = 0
    accepted: int = 0
    rejected: int = 0
    review: int = 0
    duplicates: int = 0
    observed_through: Optional[dt.date] = None
    error: Optional[str] = None


@dataclass
class CycleReport:
    started_at: str
    finished_at: str
    as_of: dt.date
    outcomes: List[SourceOutcome] = field(default_factory=list)
    discrepancies_new: int = 0


def _kind_of(name: str) -> Optional[str]:
    n = name.lower()
    return next((k for k in KINDS if n.startswith(k + "_") or n == k + ".csv"), None)


def _with_source(items, spec: SourceSpec):
    """Rows naming a source we do not know are attributed to the file's provider; provenance goes to notes."""
    out = []
    for x in items:
        if getattr(x, "source_id", "") != spec.source_id and hasattr(x, "source_id"):
            kw = {"source_id": spec.source_id}
            if hasattr(x, "notes"):
                kw["notes"] = (x.notes + " " if x.notes else "") + f"original_source_id={x.source_id or 'none'}"
            x = dataclasses.replace(x, **kw)
        out.append(x)
    return out


def _ingest_document(conn, spec: SourceSpec, doc: RawDocument, instruments: Dict[str, Instrument], as_of: dt.date,
                     retrieved_at: str, out: SourceOutcome) -> None:
    if hashlib.sha256(doc.content).hexdigest() != doc.sha256:
        raise PermanentFetchError(f"{doc.url}: content does not match its sha256")
    did = f"{spec.source_id}:{doc.sha256[:16]}"
    if not st.save_document(conn, did, spec.source_id, doc.url, retrieved_at, doc.sha256):
        out.duplicates += 1                  # already ingested: re-reading changes nothing
        return
    out.documents += 1
    kind = _kind_of(doc.url)
    try:
        text = doc.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        out.rejected += 1
        out.error = (out.error or "") + f" {doc.url}: not UTF-8;"
        return
    if kind is None:
        out.rejected += 1
        out.error = (out.error or "") + f" {doc.url}: filename must start with one of {KINDS};"
        return
    try:
        if kind == "instruments":
            rep = imp.import_instruments(text)
            st.upsert_instruments(conn, rep.accepted)
            instruments.update({i.key: i for i in rep.accepted if i.key not in instruments})
        elif kind == "distributions":
            rep = imp.import_distributions(text, instruments, as_of=as_of, known_sources={spec.source_id: spec})
            ev = _with_source(rep.accepted, spec)
            st.save_events(conn, ev, None, frozenset(), retrieved_at, did)
        elif kind == "prices":
            rep = imp.import_prices(text, instruments, as_of=as_of)
            st.save_prices(conn, _with_source(rep.accepted, spec), retrieved_at, did)
            out.observed_through = max([p.date for p in rep.accepted], default=None)
        elif kind == "navs":
            rep = imp.import_navs(text, instruments, as_of=as_of)
            st.save_navs(conn, _with_source(rep.accepted, spec), retrieved_at, did)
            out.observed_through = max([n.nav_date for n in rep.accepted], default=None)
        else:
            rep = imp.import_leverage(text, instruments, as_of=as_of)
            st.save_leverage(conn, _with_source(rep.accepted, spec), retrieved_at)
    except ValueError as e:                  # e.g. missing required column: the whole document is rejected
        out.rejected += 1
        out.error = (out.error or "") + f" {doc.url}: {e};"
        return
    run_id = f"{did}:{kind}:{retrieved_at}"
    st.save_import_run(conn, run_id, rep, retrieved_at)
    if rep.codes().get("UNKNOWN_INSTRUMENT"):   # instruments may arrive later: reprocess this file next cycle
        st.mark_document_retry(conn, spec.source_id, doc.sha256)
    out.accepted += len(rep.accepted)
    out.rejected += rep.rejected
    out.review += rep.count(imp.REVIEW)
    if kind == "distributions" and rep.accepted:
        out.observed_through = max([e.ex_date for e in rep.accepted if e.ex_date <= as_of], default=None)


def detect_discrepancies(conn, now: dt.datetime) -> List[dsc.Discrepancy]:
    """Recompute cross-source disagreements from stored observations and persist the new ones."""
    found: List[dsc.Discrepancy] = []
    for key in st.load_instruments(conn):
        groups: Dict[tuple, list] = {}
        for p, r in st.load_price_rows(conn, key):
            groups.setdefault(("price", p.date, p.venue), []).append(
                dsc.Obs(p.source_id, _grade(conn, p.source_id), p.date, p.price, r or ""))
        for n, r in st.load_nav_rows(conn, key):
            groups.setdefault(("nav", n.nav_date, n.kind), []).append(dsc.Obs(n.source_id, n.grade, n.nav_date, n.nav, r or ""))
        for lp, r in st.load_leverage_rows(conn, key):
            groups.setdefault(("leverage", lp.date, lp.definition), []).append(
                dsc.Obs(lp.source_id, lp.grade, lp.date, lp.value, r or ""))
        for (field_, *_), obs in groups.items():
            found += dsc.resolve(key, field_, obs)[1]
        _, d = dsc.reconcile_events([e for e, _ in st.load_event_rows(conn, key)])
        found += d
    st.store_discrepancies(conn, found, fr.utc_iso(now))
    return found


def _grade(conn, source_id: str) -> SourceGrade:
    r = conn.execute("SELECT grade FROM source WHERE source_id=?", (source_id,)).fetchone()
    return SourceGrade(r[0]) if r else SourceGrade.UNKNOWN


def run_cycle(conn: sqlite3.Connection, registry: Mapping[str, SourceSpec], fetchers: Mapping[str, Fetcher],
              now: Callable[[], dt.datetime], *, force: bool = False, sleep: Callable[[float], None] = time.sleep,
              limiters: Optional[Dict[str, RateLimiter]] = None, rng: Callable[[], float] = random.random,
              base_delay: float = 1.0) -> CycleReport:
    """One refresh pass over every registered source. Safe to run every hour (or more often: not-due sources are
    logged SKIPPED_NOT_DUE unless force=True)."""
    t0 = now()
    as_of = fr.ist_date(t0)
    st.sync_sources(conn, [s.to_source() for s in registry.values()])
    instruments = st.load_instruments(conn)
    limiters = limiters if limiters is not None else {}
    report = CycleReport(fr.utc_iso(t0), "", as_of)
    for sid, spec in registry.items():
        started = now()
        out = SourceOutcome(sid, "OK")
        last = st.last_attempt(conn, sid)
        if not spec.enabled:
            out.status = "SKIPPED_DISABLED"
        elif not spec.may_fetch:
            out.status = "SKIPPED_NOT_CLEARED"
        elif not force and not fr.is_due(spec, last[0] if last else None, started):
            out.status = "SKIPPED_NOT_DUE"
        elif sid not in fetchers:
            out.status, out.error = "ERROR", "no fetcher registered for a fetchable source"
        else:
            lim = limiters.setdefault(sid, RateLimiter(spec.min_interval_s, sleep=sleep))
            try:
                def attempt():
                    lim.wait()
                    return fetchers[sid].fetch(spec, as_of)
                docs, out.attempts = with_retries(attempt, spec.max_attempts, base_delay, sleep=sleep, rng=rng)
                docs = sorted(docs, key=lambda d: (KINDS.index(_kind_of(d.url)) if _kind_of(d.url) else len(KINDS), d.url))
                retrieved_at = fr.utc_iso(now())
                for doc in docs:
                    _ingest_document(conn, spec, doc, instruments, as_of, retrieved_at, out)
                out.status = "OK" if out.documents else "NO_NEW_DATA"
            except (FetchError, PermanentFetchError) as e:
                out.status, out.error = "ERROR", f"{type(e).__name__}: {e}"
        fin = now()
        n_log = conn.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0]
        st.save_retrieval(conn, f"{sid}:{fr.utc_iso(started)}:{n_log}", sid, fr.utc_iso(started), fr.utc_iso(fin),
                          out.status, out.attempts, out.documents, out.accepted, out.rejected, out.observed_through, out.error)
        conn.commit()
        report.outcomes.append(out)
    report.discrepancies_new = len([d for d in detect_discrepancies(conn, now())])
    conn.commit()
    report.finished_at = fr.utc_iso(now())
    return report


def source_statuses(conn, registry: Mapping[str, SourceSpec], now: dt.datetime) -> List[fr.SourceStatus]:
    rows = []
    for sid, spec in registry.items():
        la, ls = st.last_attempt(conn, sid), st.last_success(conn, sid)
        rows.append(fr.SourceStatus(sid, fr.classify(spec, ls[0] if ls else None, now), la[0] if la else None,
                                    la[1] if la else None, ls[0] if ls else None, ls[1] if ls else None,
                                    st.consecutive_failures(conn, sid)))
    return rows
