"""Pre-deployment gate for a built static site. Run it on the exact directory you are about to upload:

    python -m irie.cli check-site --dir dist

It checks the files, the Content-Security-Policy, that no external resource or unsafe script pattern is present, and,
most importantly, that data.json cannot leak anything: every value shown must be published (no blocking flag), attributed to
a source, and sourced only from sources recorded as display-cleared. Exit status 1 on any error.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .result import BLOCKING_FLAGS

REQUIRED = ("index.html", "app.js", "style.css", "data.json", "_headers")
SECRET_PATTERNS = [r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY", r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                   r"xox[abp]-[A-Za-z0-9-]{10,}", r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b[\"']?\s*[:=]\s*['\"][^'\"]{6,}",
                   r"sk-[A-Za-z0-9]{20,}"]
ISIN = re.compile(r"\bIN[EF][0-9A-Z]{9}\b")


@dataclass(frozen=True)
class Finding:
    level: str      # ERROR | WARN
    where: str
    message: str


def _read(d: Path, name: str) -> str:
    return (d / name).read_text(encoding="utf-8")


def check_site(directory, *, allow_preview: bool = False, allow_isin: bool = True) -> List[Finding]:
    d = Path(directory)
    out: List[Finding] = []
    err = lambda w, m: out.append(Finding("ERROR", w, m))
    warn = lambda w, m: out.append(Finding("WARN", w, m))
    for n in REQUIRED:
        if not (d / n).is_file():
            err(n, "required file is missing")
    if any(f.level == "ERROR" for f in out):
        return out
    html, js, css, hdr = _read(d, "index.html"), _read(d, "app.js"), _read(d, "style.css"), _read(d, "_headers")

    # ---- Content-Security-Policy and headers
    m = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html)
    if not m:
        err("index.html", "no Content-Security-Policy meta tag")
    else:
        csp = m.group(1)
        for need in ("default-src 'self'", "object-src 'none'", "base-uri 'none'", "form-action 'none'"):
            if need not in csp:
                err("index.html", f"CSP is missing {need!r}")
        if "'unsafe-eval'" in csp or re.search(r"script-src[^;]*'unsafe-inline'", csp) or "*" in csp.replace("'self'", ""):
            err("index.html", "CSP allows unsafe-eval, inline scripts or a wildcard")
    if "Content-Security-Policy:" not in hdr or "frame-ancestors 'none'" not in hdr:
        err("_headers", "CSP header with frame-ancestors 'none' is missing")
    for need in ("Strict-Transport-Security:", "X-Content-Type-Options: nosniff", "Referrer-Policy:"):
        if need not in hdr:
            err("_headers", f"{need} is missing")

    # ---- no external resources, no unsafe script patterns
    for name, text in (("index.html", html), ("style.css", css)):
        for u in re.findall(r"""(?:src|href|url\()\s*=?\s*["']?(https?://[^"')\s>]+)""", text):
            err(name, f"external resource reference {u}")
    for u in set(re.findall(r"https?://[^\s\"'`)]+", js)):
        if u != "http://www.w3.org/2000/svg":
            err("app.js", f"hard-coded URL {u}")
    if re.search(r"<script[^>]+src=[\"']https?:", html) or re.search(r"\son[a-z]+\s*=", html):
        err("index.html", "external script or inline event handler")
    for bad in (r"\beval\(", r"new Function\(", r"\.innerHTML\s*=", r"document\.write\(", r"\.insertAdjacentHTML\("):
        if re.search(bad, js):
            err("app.js", f"unsafe pattern {bad}")

    # ---- data.json: nothing may leak
    raw = _read(d, "data.json")
    try:
        ds = json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"non-finite {c}")))
    except ValueError as e:
        err("data.json", f"not valid JSON: {e}")
        return out
    if ds.get("preview") or ds.get("mode") != "public":
        (warn if allow_preview else err)("data.json", f"mode is {ds.get('mode')!r}: only public builds may be deployed")
    cleared = {s["id"] for s in ds.get("sources", []) if s.get("display_cleared")}
    known = {s["id"] for s in ds.get("sources", [])}
    n_values = 0
    for i in ds.get("instruments", []):
        k = i["key"]
        for name, m_ in i.get("metrics", {}).items():
            if m_.get("value") is None:
                continue
            n_values += 1
            if m_.get("status") != "OK":
                err("data.json", f"{k}.{name} has a value but status {m_.get('status')}")
            if not m_.get("sources"):
                err("data.json", f"{k}.{name} has a value with no source attribution")
            bad_src = [s_ for s_ in m_.get("sources", []) if s_ not in cleared]
            if bad_src:
                err("data.json", f"{k}.{name} shows a value from source(s) not display-cleared: {bad_src}")
            blocked = [f for f in m_.get("flags", []) if f in BLOCKING_FLAGS]
            if blocked and not allow_preview:
                err("data.json", f"{k}.{name} shows a value despite blocking flag(s) {blocked}")
            if not m_.get("publishable") and not allow_preview:
                err("data.json", f"{k}.{name} shows a value that is not marked publishable")
        for what, rec in (("price", (i.get("latest") or {}).get("price")), ("nav", (i.get("latest") or {}).get("nav"))):
            if rec and rec.get("value") is not None:
                n_values += 1
                if rec.get("source") not in cleared:
                    err("data.json", f"{k} latest {what} comes from a source that is not display-cleared ({rec.get('source')})")
                if rec.get("disputed"):
                    err("data.json", f"{k} latest {what} is disputed but shown")
        for e in (i.get("history") or {}).get("distributions", []):
            if e.get("source") not in cleared:
                err("data.json", f"{k} distribution history includes a payment from an uncleared source ({e.get('source')})")
        for h in i.get("holdings", []):
            if h.get("source") not in cleared:
                err("data.json", f"{k} holdings include a row from an uncleared source ({h.get('source')})")
        if (i.get("history") or {}).get("prices") and not (cleared & {(i.get("latest") or {}).get("price", {}) and i["latest"]["price"].get("source")}):
            err("data.json", f"{k} price history is present but its source is not display-cleared")
    for n in ds.get("news", {}).get("items", []):
        if n.get("source") not in cleared:
            err("data.json", f"news item {n.get('id')} comes from an uncleared source")
        u = n.get("url", "")
        if u and not re.match(r"^https?://", u, re.I):
            err("data.json", f"news item {n.get('id')} has an unsafe link scheme")
    for s_ in ds.get("sources", []):
        if s_.get("display_cleared") and s_["id"] not in known:
            err("data.json", "inconsistent source list")
    if ds.get("synthetic") and "SYNTHETIC" not in ds.get("notice", ""):
        err("data.json", "synthetic data without a SYNTHETIC notice")
    if not ds.get("synthetic") and cleared and n_values == 0:
        warn("data.json", "sources are display-cleared but no value is published")

    # ---- secrets and local paths
    for name in REQUIRED:
        text = _read(d, name)
        for pat in SECRET_PATTERNS:
            if re.search(pat, text):
                err(name, f"possible secret matching {pat}")
        if re.search(r"(/home/|/root/|/tmp/|[A-Za-z]:\\\\Users)", text):
            err(name, "contains a local filesystem path")
        if re.search(r"\.sqlite|\.db\b", text):
            warn(name, "mentions a database file name")
    if not allow_isin and ISIN.search(raw):
        warn("data.json", "contains ISIN-shaped identifiers")
    extra = sorted(p.name for p in d.iterdir() if p.name not in REQUIRED)
    if extra:
        warn(str(d), f"unexpected extra files will be uploaded: {extra}")
    return out
