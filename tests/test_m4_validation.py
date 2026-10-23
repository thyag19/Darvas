"""M4 validation: pre-deployment site gate, determinism, no real/restricted data in the demo or the repository, secrets,
and stale / conflicting / withheld data end to end."""
import dataclasses
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from irie import cli, demo, export, ingest, site, storage as st
from irie.calc.distributions import ComponentStatus, component_status, components_verified
from irie.market_calendar import load_calendar
from irie.models import ComponentType as C
from irie.sitecheck import ISIN, SECRET_PATTERNS, check_site

ROOT = Path(__file__).resolve().parent.parent
CAL = load_calendar(ROOT / "config" / "market_calendar.json")


def build_demo_site(out: Path, registry=None, writer=None, tmp: Path = None) -> Path:
    tmp = tmp or out.parent / (out.name + "-inbox")
    (writer or demo.write_demo_inbox)(tmp)
    conn = st.connect(); st.init_schema(conn)
    reg = registry or demo.demo_registry()
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(tmp, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW, calendar=CAL)
    site.build_site(export.dumps(export.build_dataset(conn, reg, demo.DEMO_NOW, "public", CAL)), out)
    return out


@pytest.fixture(scope="module")
def good(tmp_path_factory):
    return build_demo_site(tmp_path_factory.mktemp("good") / "site")


def errors(d, **kw):
    return [f for f in check_site(d, **kw) if f.level == "ERROR"]


def mutate(good, tmp_path, fn, name="data.json", text=True):
    d = tmp_path / "m"
    shutil.copytree(good, d)
    p = d / name
    if name == "data.json":
        ds = json.loads(p.read_text()); fn(ds); p.write_text(json.dumps(ds))
    else:
        p.write_text(fn(p.read_text()))
    return d


# ---- the pre-deployment gate ------------------------------------------------------------------------------------------
def test_clean_builds_pass_the_gate_including_nothing_cleared(good, tmp_path):
    assert check_site(good) == []
    reg = {k: dataclasses.replace(v, display_cleared=False, display_evidence="") for k, v in demo.demo_registry().items()}
    closed = build_demo_site(tmp_path / "closed", registry=reg)
    assert errors(closed) == []
    ds = json.loads((closed / "data.json").read_text())
    assert all(m["value"] is None for i in ds["instruments"] for m in i["metrics"].values())


def test_cli_check_site_exit_codes(good, tmp_path, capsys):
    assert cli.main(["check-site", "--dir", str(good)]) == 0
    bad = mutate(good, tmp_path, lambda ds: ds.update(mode="preview", preview=True))
    assert cli.main(["check-site", "--dir", str(bad)]) == 1
    assert "only public builds may be deployed" in capsys.readouterr().out


LEAKS = {
    "preview mode": (lambda ds: ds.update(mode="preview", preview=True), "only public builds"),
    "value shown despite blocking flag": (lambda ds: next(i for i in ds["instruments"] if i["key"] == "DEMO_INVIT_C")["metrics"]["ttm_yield"].update(value=0.1), "blocking flag"),
    "value from an uncleared source": (lambda ds: [s.update(display_cleared=False) for s in ds["sources"]], "not display-cleared"),
    "value with no attribution": (lambda ds: next(i for i in ds["instruments"] if i["key"] == "DEMO_INVIT_A")["metrics"]["ttm_yield"].update(sources=[]), "no source attribution"),
    "value on an unavailable metric": (lambda ds: next(i for i in ds["instruments"] if i["key"] == "DEMO_INVIT_B")["metrics"]["income_yield"].update(value=0.0), "status UNAVAILABLE"),
    "disputed price shown": (lambda ds: next(i for i in ds["instruments"] if i["key"] == "DEMO_REIT_A")["latest"]["price"].update(value=316.2), "disputed but shown"),
    "news from uncleared source": (lambda ds: ds["news"]["items"][0].update(source="NOPE"), "uncleared source"),
    "javascript news link": (lambda ds: ds["news"]["items"][0].update(url="javascript:alert(1)"), "unsafe link scheme"),
    "history from uncleared source": (lambda ds: next(i for i in ds["instruments"] if i["key"] == "DEMO_INVIT_A")["history"]["distributions"][0].update(source="NOPE"), "uncleared source"),
    "synthetic without notice": (lambda ds: ds.update(notice="all good"), "SYNTHETIC notice"),
    "secret in data": (lambda ds: ds.update(config={"password": "hunter2hunter2"}), "possible secret"),
    "local path in data": (lambda ds: ds.update(path="/home/user/Darvas/irie.sqlite"), "local filesystem path"),
}


@pytest.mark.parametrize("name", list(LEAKS))
def test_the_gate_catches_each_kind_of_leak(good, tmp_path, name):
    fn, needle = LEAKS[name]
    found = errors(mutate(good, tmp_path, fn))
    assert any(needle in f.message for f in found), (name, [f.message for f in found])


@pytest.mark.parametrize("fn,needle,file", [
    (lambda t: t + "\nconst x = eval('1');", "unsafe pattern", "app.js"),
    (lambda t: t + "\nel.innerHTML = 'x';", "unsafe pattern", "app.js"),
    (lambda t: t + "\nfetch('https://tracker.example/p');", "hard-coded URL", "app.js"),
    (lambda t: t.replace("</body>", '<script src="https://cdn.example/x.js"></script></body>'), "external", "index.html"),
    (lambda t: t.replace("<body>", '<body onload="x()">'), "inline event handler", "index.html"),
    (lambda t: re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", t), "no Content-Security-Policy", "index.html"),
    (lambda t: t.replace("default-src 'self';", "default-src *;"), "CSP is missing", "index.html"),
    (lambda t: t.replace("object-src 'none'", "object-src 'self' 'unsafe-eval'"), "CSP", "index.html"),
    (lambda t: t + "\n@import url('https://fonts.example/f.css');", "external resource", "style.css"),
    (lambda t: t.replace("Strict-Transport-Security", "X-Other"), "Strict-Transport-Security", "_headers"),
    (lambda t: t.replace("frame-ancestors 'none'", ""), "frame-ancestors", "_headers"),
])
def test_the_gate_catches_unsafe_code_and_missing_headers(good, tmp_path, fn, needle, file):
    found = errors(mutate(good, tmp_path, fn, name=file))
    assert any(needle in f.message for f in found), [f.message for f in found]


def test_the_gate_rejects_missing_files_and_non_finite_json(good, tmp_path):
    d = tmp_path / "x"; shutil.copytree(good, d); (d / "data.json").unlink()
    assert any("missing" in f.message for f in errors(d))
    d2 = tmp_path / "y"; shutil.copytree(good, d2)
    (d2 / "data.json").write_text((good / "data.json").read_text().replace('"as_of"', '"nan_field": NaN, "as_of"', 1))
    assert any("not valid JSON" in f.message for f in errors(d2))


# ---- repeatable build ---------------------------------------------------------------------------------------------------
def tree_hash(d: Path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())}


def test_the_demo_build_is_byte_for_byte_repeatable(tmp_path):
    a = build_demo_site(tmp_path / "a" / "site", tmp=tmp_path / "ia")
    b = build_demo_site(tmp_path / "b" / "site", tmp=tmp_path / "ib")
    assert tree_hash(a) == tree_hash(b) and set(tree_hash(a)) == {"index.html", "app.js", "style.css", "data.json", "_headers"}


def test_every_shipped_web_file_is_packaged():
    import tomllib
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "web/*" in meta["tool"]["setuptools"]["package-data"]["irie"]
    web = {p.name for p in (ROOT / "irie" / "web").iterdir()}
    assert web == {"index.html", "app.js", "style.css", "_headers"}


# ---- no real or restricted data, no secrets -------------------------------------------------------------------------
REAL_NAMES = ["IndiGrid", "Embassy", "Mindspace", "Nexus", "Brookfield", "PowerGrid", "POWERGRID", "IRB ", "Cube Highways", "Altius", "Vertis",
              "Anzen", "NHIT", "Shrem", "Nippon", "HDFC", "ICICI", "Kotak", "Nifty", "Sensex", "Dhan"]


def test_the_synthetic_demo_contains_nothing_real(good, tmp_path):
    inbox = tmp_path / "inbox"; demo.write_demo_inbox(inbox)
    blobs = {str(p): p.read_text() for p in inbox.rglob("*.csv")}
    blobs.update({p.name: p.read_text() for p in good.iterdir()})
    blobs["demo.py"] = (ROOT / "irie" / "demo.py").read_text()
    for where, text in blobs.items():
        assert not ISIN.search(text), f"ISIN-shaped identifier in {where}"
        for n in REAL_NAMES:
            assert n not in text, f"real-looking name {n!r} in {where}"
    ds = json.loads((good / "data.json").read_text())
    assert all(i["key"].startswith("DEMO_") and "(synthetic)" in i["name"] and i["isin"] is None for i in ds["instruments"])
    assert all(n["url"].startswith("https://example.invalid/") and n["synthetic"] for n in ds["news"]["items"])
    assert {p["venue"] for i in ds["instruments"] for p in [i["latest"]["price"]] if p} == {"DEMO-EXCH"}      # no real exchange label on invented prices
    assert all(s["synthetic"] and s["id"].startswith("DEMO") for s in ds["sources"])


def tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    except Exception:
        pytest.skip("not a git checkout")
    return [f for f in out if f]


def test_no_restricted_data_or_private_fixtures_are_tracked():
    files = tracked()
    assert not [f for f in files if f.startswith("tests/fixtures/")], "private workbook fixtures must stay untracked"
    assert not [f for f in files if f.endswith((".xlsx", ".xls", ".sqlite", ".db"))]
    assert not [f for f in files if f.startswith("inbox/")]
    hits = []
    for f in files:
        p = ROOT / f
        if p.suffix in (".png", ".ico") or not p.is_file():
            continue
        text = p.read_text(errors="ignore")
        if ISIN.search(text):
            hits.append(f)
    assert hits == [], f"ISIN-shaped identifiers in tracked files: {hits}"


def test_no_secrets_in_tracked_files():
    hits = []
    for f in tracked():
        p = ROOT / f
        if p.suffix in (".png", ".ico", ".pdf") or not p.is_file() or f in ("irie/sitecheck.py", "tests/test_m4_validation.py"):
            continue
        text = p.read_text(errors="ignore")
        for pat in SECRET_PATTERNS:
            if re.search(pat, text):
                hits.append((f, pat))
    assert hits == [], hits


def test_workflows_hold_no_secrets_and_never_deploy():
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        t = wf.read_text()
        assert "secrets." not in t and "deploy" not in t.lower().replace("deploys nothing", ""), wf.name
        assert "permissions:" in t and "contents: read" in t


# ---- stale, conflicting, withheld data end to end ---------------------------------------------------------------------
def write_case(root: Path):
    for d in ("DEMO", "DEMO2"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "DEMO" / "instruments_a.csv").write_text("key,name,type\nI1,Conflict Trust (synthetic),INVIT\nI2,Stale Trust (synthetic),INVIT\n")
    dh = "instrument_key,ex_date,total_per_unit,interest,capital_repayment,amount_grade\n"
    for k in ("I1", "I2"):
        dh += f"{k},2026-08-01,3.0,2.5,0.5,ISSUER\n{k},2026-05-01,2.0,1.5,0.5,ISSUER\n"
    (root / "DEMO" / "distributions_a.csv").write_text(dh)
    (root / "DEMO2" / "distributions_b.csv").write_text("instrument_key,ex_date,total_per_unit,amount_grade\nI1,2026-08-01,4.0,ISSUER\n")
    (root / "DEMO" / "prices_a.csv").write_text("instrument_key,date,price,venue\nI1,2026-10-21,100,DEMO-EXCH\nI2,2026-10-15,100,DEMO-EXCH\n")
    (root / "DEMO" / "navs_a.csv").write_text("instrument_key,nav_date,nav,kind,grade\nI2,2025-12-31,95,FAIR_VALUE,ISSUER\n")


def test_stale_conflicting_and_withheld_data_never_reaches_the_public_build(tmp_path):
    out = build_demo_site(tmp_path / "site", writer=write_case)
    assert errors(out) == []
    ds = {i["key"]: i for i in json.loads((out / "data.json").read_text())["instruments"]}
    i1, i2 = ds["I1"]["metrics"], ds["I2"]["metrics"]
    # conflicting equal-grade amounts -> the date becomes amount-unavailable, a lower bound, flagged and withheld
    assert "AMOUNT_UNAVAILABLE_IN_WINDOW" in i1["ttm_dpu"]["flags"] and i1["ttm_dpu"]["value"] is None and i1["ttm_dpu"]["withheld"]
    assert ds["I1"]["open_discrepancies"] and ds["I1"]["open_discrepancies"][0]["field"] == "distribution"
    assert "SOURCE_DISCREPANCY" in i1["ttm_dpu"]["flags"]
    # a 7-day-old price is stale: figure computed but blocked; the price itself is shown only as an observation with its date
    assert "PRICE_STALE" in i2["ttm_yield"]["flags"] and i2["ttm_yield"]["value"] is None and i2["ttm_yield"]["withheld"]
    # stale NAV (294 days) is flagged and withheld too
    assert "NAV_STALE" in i2["premium_to_nav"]["flags"] and i2["premium_to_nav"]["value"] is None
    assert ds["I2"]["latest"]["price"]["date"] == "2026-10-15"


def test_reit_components_including_rental_and_return_of_capital_reconcile(tmp_path):
    inbox = tmp_path / "in"; demo.write_demo_inbox(inbox)
    conn = st.connect(); st.init_schema(conn); reg = demo.demo_registry()
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(inbox, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW, calendar=CAL)
    events = [e for e, _ in st.load_event_rows(conn, "DEMO_REIT_A")]
    assert len(events) == 8
    for e in events:
        assert component_status(e) is ComponentStatus.RECONCILES and components_verified(e), e.event_id
        assert {C.INTEREST, C.DIVIDEND, C.RENTAL, C.CAPITAL_REPAYMENT} <= set(e.components)
        assert e.components[C.CAPITAL_REPAYMENT] > 0 and e.components[C.RENTAL] > e.components[C.CAPITAL_REPAYMENT]
        assert abs(sum(e.components.values()) - e.total_per_unit) <= type(e.total_per_unit)("0.0051")


def test_cli_calendar_handling_for_installed_use(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)                                    # no ./config here, as after `pip install`
    missing = str(tmp_path / "nope.json")
    assert cli.main(["build-demo", "--out", str(tmp_path / "d"), "--calendar", missing]) == 0       # the demo can run without a calendar
    ds = json.loads((tmp_path / "d" / "data.json").read_text())
    assert ds["market"] == {"known": False} and check_site(tmp_path / "d") == []
    assert cli.main(["run-cycle", "--db", str(tmp_path / "x.sqlite"), "--registry", str(ROOT / "config" / "sources.json"), "--calendar", missing,
                     "--inbox", str(tmp_path / "in")]) == 2                                          # real scheduling refuses to run blind
    assert "market calendar not found" in capsys.readouterr().err
