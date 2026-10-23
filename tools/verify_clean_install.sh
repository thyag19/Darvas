#!/usr/bin/env bash
# Verifies that a fresh checkout installs and builds from nothing: new virtualenv, `pip install .`, synthetic demo build run from the
# INSTALLED package (not the source tree), the pre-deploy gate, and a repeatability check. Uses only PyPI for build tooling.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet "$ROOT"
cd "$WORK"                                   # leave the source tree so only the installed package can be imported
"$WORK/venv/bin/python" -c "import irie, pathlib; p = pathlib.Path(irie.__file__).parent; assert 'site-packages' in str(p), p; assert (p/'schema.sql').exists() and (p/'web'/'index.html').exists() and (p/'web'/'_headers').exists(); print('installed package:', p)"
cp -r "$ROOT/config" "$WORK/config"
"$WORK/venv/bin/python" -m irie.cli build-demo --out "$WORK/site1" --calendar "$WORK/config/market_calendar.json"
"$WORK/venv/bin/python" -m irie.cli build-demo --out "$WORK/site2" --calendar "$WORK/config/market_calendar.json"
"$WORK/venv/bin/python" -m irie.cli check-site --dir "$WORK/site1"
diff -r "$WORK/site1" "$WORK/site2" && echo "repeatable: two builds are byte-identical"
"$WORK/venv/bin/python" -m irie.cli run-cycle --db "$WORK/t.sqlite" --registry "$WORK/config/sources.json" --calendar "$WORK/config/market_calendar.json" --inbox "$WORK/inbox" | head -c 400; echo
"$WORK/venv/bin/python" -m irie.cli build-site --db "$WORK/t.sqlite" --registry "$WORK/config/sources.json" --calendar "$WORK/config/market_calendar.json" --out "$WORK/pub"
"$WORK/venv/bin/python" -m irie.cli check-site --dir "$WORK/pub"
echo "CLEAN INSTALL OK"
