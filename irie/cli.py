"""Command line: validate input files and print metrics. Reads local files only; no network access.

  python -m irie.cli validate-distributions --instruments I.csv --file D.csv [--as-of 2026-10-21]
  python -m irie.cli metrics --bundle tests/fixtures/invit_workbook_v4 [--as-of 2026-10-21]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from .importing import import_distributions
from .registry import Snapshot, compute_all
from .seed import _rows, load_bundle
from .models import Instrument, InstrumentType


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="irie")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate-distributions")
    v.add_argument("--instruments", required=True)
    v.add_argument("--file", required=True)
    v.add_argument("--as-of")
    m = sub.add_parser("metrics")
    m.add_argument("--bundle", required=True)
    m.add_argument("--as-of")
    r = sub.add_parser("run-cycle", help="refresh every registered source once (or hourly with --loop)")
    r.add_argument("--db", required=True)
    r.add_argument("--registry", default="config/sources.json")
    r.add_argument("--calendar", default="config/market_calendar.json")
    r.add_argument("--inbox", default="inbox")
    r.add_argument("--force", action="store_true")
    r.add_argument("--loop", action="store_true", help="repeat forever, sleeping --interval seconds between cycles")
    r.add_argument("--interval", type=int, default=900, help="seconds between scheduling passes; the scheduler decides what is due")
    b = sub.add_parser("build-site", help="write the static dashboard from the database")
    b.add_argument("--db", required=True)
    b.add_argument("--registry", default="config/sources.json")
    b.add_argument("--calendar", default="config/market_calendar.json")
    b.add_argument("--out", required=True)
    b.add_argument("--mode", choices=["public", "preview"], default="public")
    d = sub.add_parser("build-demo", help="build the dashboard from SYNTHETIC data (never real market data)")
    d.add_argument("--out", required=True)
    d.add_argument("--calendar", default=None, help="market calendar JSON (default: ./config/market_calendar.json if present)")
    c = sub.add_parser("check-site", help="pre-deployment gate: CSP, external references, data leaks, secrets")
    c.add_argument("--dir", required=True)
    c.add_argument("--allow-preview", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "check-site":
        from .sitecheck import check_site
        findings = check_site(a.dir, allow_preview=a.allow_preview)
        for f in findings:
            print(f"{f.level}: {f.where}: {f.message}")
        errors = [f for f in findings if f.level == "ERROR"]
        print(f"site check: {len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
        return 1 if errors else 0
    if a.cmd in ("run-cycle", "build-site", "build-demo"):
        return _operate(a)
    as_of = dt.date.fromisoformat(a.as_of) if a.as_of else None
    if a.cmd == "validate-distributions":
        inst = {r["key"]: Instrument(r["key"], r["name"], InstrumentType(r["type"])) for r in _rows(Path(a.instruments))}
        rep = import_distributions(Path(a.file).read_text(encoding="utf-8"), inst, as_of=as_of)
        print(rep.to_json())
        return 1 if rep.rejected else 0
    b = load_bundle(a.bundle)
    as_of = as_of or b.as_of
    out = {}
    for key, inst in b.instruments.items():
        snap = Snapshot(inst, as_of, [e for e in b.events if e.instrument_key == key], b.prices.get(key),
                        b.navs.get(key), leverage=b.leverage.get(key))
        out[key] = {n: {"status": r.status.value, "value": None if r.value is None else str(r.value),
                        "flags": list(r.flags), "reasons": list(r.reasons)}
                    for n, r in compute_all(snap).items() if r.status.value != "NOT_APPLICABLE"}
    print(json.dumps({"as_of": as_of.isoformat(), "instruments": out}, indent=1, sort_keys=True))
    return 0


def _operate(a) -> int:
    import tempfile
    import time
    from . import demo, export, ingest, site
    from . import storage as st
    from .market_calendar import load_calendar
    from .sources import load_registry
    arg = getattr(a, "calendar", None)
    candidates = [Path(arg)] if arg else [Path("config/market_calendar.json"), Path(__file__).resolve().parent.parent / "config" / "market_calendar.json"]
    cal_path = next((c for c in candidates if c.exists()), None)
    if cal_path is None and a.cmd != "build-demo":
        print(f"error: market calendar not found ({', '.join(map(str, candidates))}); market-hours scheduling needs it", file=sys.stderr)
        return 2

    utcnow = lambda: dt.datetime.now(dt.timezone.utc)
    if a.cmd == "build-demo":
        with tempfile.TemporaryDirectory() as tmp:
            demo.write_demo_inbox(tmp)
            conn = st.connect()
            st.init_schema(conn)
            reg = demo.demo_registry()
            fetchers = {k: ingest.FileInboxFetcher(tmp, lambda: demo.DEMO_NOW) for k in reg}
            cal = load_calendar(cal_path) if cal_path else None      # a demo without a calendar simply shows 'calendar not loaded'
            rep = ingest.run_cycle(conn, reg, fetchers, lambda: demo.DEMO_NOW, calendar=cal)
            ds = export.build_dataset(conn, reg, demo.DEMO_NOW, "public", cal)
            site.build_site(export.dumps(ds), a.out)
        print(f"demo site written to {a.out} ({len(ds['instruments'])} synthetic instruments)")
        return 0
    registry = load_registry(a.registry)
    cal = load_calendar(cal_path)
    for sp in registry.values():
        from .scheduler import validate_schedule
        validate_schedule(sp, cal)
    conn = st.connect(a.db)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='source'").fetchone():
        st.init_schema(conn)
    if a.cmd == "build-site":
        site.build_site(export.dumps(export.build_dataset(conn, registry, utcnow(), a.mode, cal)), a.out)
        print(f"{a.mode} site written to {a.out}")
        return 0
    fetchers = {sid: ingest.FileInboxFetcher(a.inbox, utcnow) for sid, sp in registry.items() if sp.kind == "file_inbox"}
    while True:
        rep = ingest.run_cycle(conn, registry, fetchers, utcnow, calendar=cal, force=a.force)
        print(json.dumps({"started_at": rep.started_at, "finished_at": rep.finished_at, "as_of": rep.as_of.isoformat(),
                          "discrepancies": rep.discrepancies_new,
                          "sources": {o.source_id: {"status": o.status, "documents": o.documents, "accepted": o.accepted,
                                                    "rejected": o.rejected, "error": o.error} for o in rep.outcomes}},
                         sort_keys=True), flush=True)
        if not a.loop:
            return 1 if any(o.status == "ERROR" for o in rep.outcomes) else 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
