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
    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
