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
    r.add_argument("--inbox", default="inbox")
    r.add_argument("--force", action="store_true")
    r.add_argument("--loop", action="store_true", help="repeat forever, sleeping --interval seconds between cycles")
    r.add_argument("--interval", type=int, default=3600)
    b = sub.add_parser("build-site", help="write the static dashboard from the database")
    b.add_argument("--db", required=True)
    b.add_argument("--registry", default="config/sources.json")
    b.add_argument("--out", required=True)
    b.add_argument("--mode", choices=["public", "preview"], default="public")
    d = sub.add_parser("build-demo", help="build the dashboard from SYNTHETIC data (never real market data)")
    d.add_argument("--out", required=True)
    a = ap.parse_args(argv)
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
    from .sources import load_registry

    utcnow = lambda: dt.datetime.now(dt.timezone.utc)
    if a.cmd == "build-demo":
        with tempfile.TemporaryDirectory() as tmp:
            demo.write_demo_inbox(tmp)
            conn = st.connect()
            st.init_schema(conn)
            reg = demo.demo_registry()
            fetchers = {k: ingest.FileInboxFetcher(tmp, lambda: demo.DEMO_NOW) for k in reg}
            rep = ingest.run_cycle(conn, reg, fetchers, lambda: demo.DEMO_NOW)
            ds = export.build_dataset(conn, reg, demo.DEMO_NOW, "public")
            ds["notice"] = "SYNTHETIC DEMO DATA: invented by irie.demo. Not real market data."
            site.build_site(export.dumps(ds), a.out)
        print(f"demo site written to {a.out} ({len(ds['instruments'])} synthetic instruments)")
        return 0
    registry = load_registry(a.registry)
    conn = st.connect(a.db)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='source'").fetchone():
        st.init_schema(conn)
    if a.cmd == "build-site":
        site.build_site(export.dumps(export.build_dataset(conn, registry, utcnow(), a.mode)), a.out)
        print(f"{a.mode} site written to {a.out}")
        return 0
    fetchers = {sid: ingest.FileInboxFetcher(a.inbox, utcnow) for sid, sp in registry.items() if sp.kind == "file_inbox"}
    while True:
        rep = ingest.run_cycle(conn, registry, fetchers, utcnow, force=a.force)
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
