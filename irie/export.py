"""Build the dashboard dataset (data.json) from the database.

Two modes:
  public   only values whose sources are display_cleared AND whose metric carries no blocking flag are included;
           everything else is withheld with its reasons. With no cleared source the public dataset contains
           instrument identities and source/freshness status only.
  preview  every value is included, marked preview=True, for the operator's own inspection. NEVER deploy a preview build.
The dashboard only displays what this file contains; it computes no metrics itself.
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Dict, List, Mapping, Optional

from . import discrepancy as dsc
from . import freshness as fr
from . import ingest
from . import storage as st
from .calc.common import ttm_window
from .calc.distributions import Coverage, components_verified, summarize_window
from .market_calendar import MarketCalendar
from .models import COMPONENT_CLASS, ComponentClass, ComponentType, InstrumentType, NavKind
from .registry import Snapshot, compute_all
from .result import MetricResult, publish_decision
from .sources import SourceSpec

SCHEMA_VERSION = 1
ALERT_TYPES = [
    {"id": "price_above", "label": "Last price above ₹", "metric": "price", "param": "rupees"},
    {"id": "price_below", "label": "Last price below ₹", "metric": "price", "param": "rupees"},
    {"id": "yield_above", "label": "Headline TTM yield above %", "metric": "ttm_yield", "param": "percent"},
    {"id": "yield_below", "label": "Headline TTM yield below %", "metric": "ttm_yield", "param": "percent"},
    {"id": "premium_above", "label": "Premium to NAV above %", "metric": "premium_to_nav", "param": "percent"},
    {"id": "discount_below", "label": "Premium/discount to NAV below %", "metric": "premium_to_nav", "param": "percent"},
    {"id": "capital_share_above", "label": "Capital-repayment share above %", "metric": "capital_repayment_share", "param": "percent"},
    {"id": "data_stale", "label": "Price data older than N hours", "metric": "price", "param": "hours"},
]


def _num(v: Optional[Decimal]) -> Optional[float]:
    return None if v is None else float(v)


def _latest_resolved(rows, field: str, key: str, by):
    """rows: [(point, retrieved_at)]. Resolve each observation identity across sources; return resolved list of
    (point, retrieved_at, obs) for identities that resolved, sorted by date."""
    groups: Dict[tuple, list] = {}
    for pt, r in rows:
        groups.setdefault(by(pt), []).append((pt, r))
    out = []
    for ident, items in groups.items():
        obs = [dsc.Obs(p.source_id, getattr(p, "grade", None) or _GR[p.source_id], _d(p), _v(p), r or "") for p, r in items]
        chosen, _ = dsc.resolve(key, field, obs)
        if chosen is not None:
            p, r = next((p, r) for p, r in items if p.source_id == chosen.source_id)
            out.append((p, r))
    return sorted(out, key=lambda x: _d(x[0]))


_GR: Dict[str, object] = {}


def _d(p):
    return getattr(p, "date", None) or getattr(p, "nav_date")


def _v(p):
    return getattr(p, "price", None) if hasattr(p, "price") else p.nav


def _metric_json(name: str, r: MetricResult, sources, mode: str) -> dict:
    publishable, why = publish_decision(r, sources)
    show = r.ok and (publishable or mode == "preview")
    return {"status": r.status.value, "value": _num(r.value) if show else None, "unit": r.unit,
            "flags": list(r.flags), "reasons": list(r.reasons), "sources": list(r.source_ids),
            "publishable": publishable, "withheld": bool(r.ok and not show), "withheld_reasons": [] if show else why}


def build_dataset(conn, registry: Mapping[str, SourceSpec], now: dt.datetime, mode: str = "public",
                  calendar: Optional[MarketCalendar] = None) -> dict:
    if mode not in ("public", "preview"):
        raise ValueError(mode)
    as_of = fr.ist_date(now)
    sources = st.load_sources(conn)
    _GR.clear()
    _GR.update({sid: s.grade for sid, s in sources.items()})
    open_d: Dict[str, List[dsc.Discrepancy]] = {}
    for key, field, ref, sa, va, sb, vb in conn.execute(
            "SELECT instrument_key,field,ref_date,source_a,value_a,source_b,value_b FROM discrepancy WHERE status='OPEN'"):
        open_d.setdefault(key, []).append(dsc.Discrepancy(key, field, dt.date.fromisoformat(ref), sa, Decimal(va), sb, Decimal(vb)))
    instruments = []
    for key, inst in st.load_instruments(conn).items():
        ev_rows = st.load_event_rows(conn, key)
        retrieved = {e.event_id: r for e, r in ev_rows}
        events, _ = dsc.reconcile_events([e for e, _ in ev_rows])
        price_hist = _latest_resolved(st.load_price_rows(conn, key), "price", key, lambda p: (p.date, p.venue))
        want = NavKind.FUND_NAV if inst.type is InstrumentType.ETF else NavKind.FAIR_VALUE
        nav_hist = _latest_resolved([x for x in st.load_nav_rows(conn, key) if x[0].kind is want], "nav", key,
                                    lambda n: (n.nav_date, n.kind))
        lev_rows = st.load_leverage_rows(conn, key)
        lev = max(lev_rows, key=lambda x: x[0].date)[0] if lev_rows else None
        price = price_hist[-1] if price_hist else None
        nav = nav_hist[-1] if nav_hist else None
        holds = st.load_holdings(conn, key) if inst.type is InstrumentType.ETF else []
        snap = Snapshot(inst, as_of, events, price[0] if price else None, nav[0] if nav else None,
                        [n for n, _ in nav_hist], lev, holdings=holds)
        results = dsc.apply_flags(compute_all(snap), open_d.get(key, []))

        def cleared(sid):
            s = sources.get(sid)
            return mode == "preview" or bool(s and s.display_cleared)

        dist_hist = []
        for e in sorted(events, key=lambda e: e.ex_date):
            if not (e.include and e.total_per_unit is not None) or not cleared(e.source_id):
                continue
            split = None
            if components_verified(e):
                split = {c.value.lower(): _num(sum((v for t, v in e.components.items() if COMPONENT_CLASS[t] is c), Decimal(0)))
                         for c in ComponentClass}
            dist_hist.append({"ex_date": e.ex_date.isoformat(), "total": _num(e.total_per_unit), "split": split,
                              "grade": e.amount_grade.value, "source": e.source_id, "retrieved_at": retrieved.get(e.event_id)})
        breakdown = _breakdown(inst, events, as_of, results, sources, mode)
        trend = _yield_trend(inst, events, price_hist, sources, mode,
                             skip_dates={d.ref_date for d in open_d.get(key, []) if d.field == "price"})
        top_holdings = []
        if holds:
            latest = max(h.as_of for h in holds)
            top_holdings = [{"name": h.name, "isin": h.isin, "weight": _num(h.weight), "as_of": latest.isoformat(), "source": h.source_id}
                            for h in sorted((h for h in holds if h.as_of == latest), key=lambda h: -h.weight)[:10] if cleared(h.source_id)]
        instruments.append({
            "key": key, "name": inst.name, "type": inst.type.value,
            "etf_category": inst.etf_category.value if inst.etf_category else None, "isin": inst.isin,
            "metrics": {n: _metric_json(n, r, sources, mode) for n, r in results.items()
                        if r.status.value != "NOT_APPLICABLE"},
            "latest": {
                "price": None if not price else {"value": _num(price[0].price) if cleared(price[0].source_id) else None,
                                                 "date": price[0].date.isoformat(), "venue": price[0].venue,
                                                 "source": price[0].source_id, "retrieved_at": price[1]},
                "nav": None if not nav else {"value": _num(nav[0].nav) if cleared(nav[0].source_id) else None,
                                             "date": nav[0].nav_date.isoformat(), "source": nav[0].source_id,
                                             "grade": nav[0].grade.value, "retrieved_at": nav[1]}},
            "breakdown": breakdown, "holdings": top_holdings,
            "history": {"distributions": dist_hist, "yield_trend": trend,
                        "prices": [[p.date.isoformat(), _num(p.price)] for p, _ in price_hist if cleared(p.source_id)],
                        "navs": [[n.nav_date.isoformat(), _num(n.nav)] for n, _ in nav_hist if cleared(n.source_id)]},
            "open_discrepancies": [{"field": d.field, "date": d.ref_date.isoformat(), "a": d.source_a, "b": d.source_b}
                                   for d in open_d.get(key, [])]})
    stat = ingest.source_statuses(conn, registry, now, calendar)
    news = _news(conn, registry, sources, mode)
    return {
        "schema_version": SCHEMA_VERSION, "mode": mode, "preview": mode == "preview",
        "generated_at": fr.utc_iso(now), "as_of": as_of.isoformat(),
        "notice": ("PREVIEW BUILD - contains values from sources not cleared for display. Do not deploy."
                   if mode == "preview" else
                   "SYNTHETIC DEMO DATA: invented by irie.demo. Not real market data."
                   if any(r.synthetic for r in registry.values()) else
                   "Values are shown only for sources recorded as cleared for display. Informational only; not investment advice."),
        "sources": [{"id": s.source_id, "name": registry[s.source_id].name, "grade": registry[s.source_id].grade.value,
                     "access": registry[s.source_id].access.value, "display_cleared": registry[s.source_id].display_cleared,
                     "freshness": s.freshness.value, "last_attempt_at": s.last_attempt_at,
                     "last_attempt_status": s.last_attempt_status, "last_success_at": s.last_success_at,
                     "observed_through": s.observed_through, "consecutive_failures": s.consecutive_failures,
                     "terms_url": registry[s.source_id].terms_url, "schedule": s.schedule,
                     "next_attempt_at": s.next_attempt_at, "synthetic": registry[s.source_id].synthetic,
                     "may_fetch": registry[s.source_id].may_fetch} for s in stat],
        "market": _market(calendar, now), "news": news,
        "synthetic": any(r.synthetic for r in registry.values()),
        "instruments": instruments, "alert_types": ALERT_TYPES}


def _market(cal: Optional[MarketCalendar], now: dt.datetime) -> dict:
    if cal is None:
        return {"known": False}
    st_ = cal.status(now)
    no = cal.next_open(now)
    return {"known": True, "open": st_.open, "reason": st_.reason, "holiday": st_.holiday_name, "calendar_loaded": st_.calendar_loaded,
            "calendar_verified": st_.verified, "next_open": fr.utc_iso(no) if no else None,
            "session": f"{cal.regular[0]:%H:%M}-{cal.regular[1]:%H:%M} IST"}


def _news(conn, registry, sources, mode) -> dict:
    items, withheld = [], 0
    for n, retrieved in st.load_news(conn):
        s = sources.get(n.source_id)
        if not (mode == "preview" or (s and s.display_cleared)):
            withheld += 1
            continue
        spec = registry.get(n.source_id)
        items.append({"id": n.news_id, "published_at": n.published_at, "retrieved_at": retrieved, "source": n.source_id,
                      "source_name": s.name if s else n.source_id, "publisher": n.publisher, "category": n.category,
                      "instrument_key": n.instrument_key, "headline": n.headline, "summary": n.summary, "url": n.url,
                      "synthetic": bool(spec and spec.synthetic)})
    feeds = [r for r in registry.values() if "news" in r.provides and r.may_fetch]
    return {"items": items, "withheld": withheld, "feed_connected": bool(feeds),
            "feeds": [{"id": r.source_id, "name": r.name, "access": r.access.value} for r in registry.values() if "news" in r.provides]}


COMP_ORDER = (ComponentType.INTEREST, ComponentType.DIVIDEND, ComponentType.RENTAL, ComponentType.OTHER_INCOME,
              ComponentType.CAPITAL_REPAYMENT)


def _breakdown(inst, events, as_of, results, sources, mode) -> Optional[dict]:
    if inst.type is InstrumentType.ETF:
        return None
    t0, t1 = ttm_window(as_of)
    w = summarize_window(events, t0, t1)
    res = results.get("ttm_dpu")
    pub = bool(res and res.ok and (mode == "preview" or publish_decision(res, sources)[0]))
    if w.n == 0 or not pub:
        return {"coverage": w.coverage.value, "available": False, "reason": "no published TTM distribution"}
    if w.coverage is not Coverage.COMPLETE:
        return {"coverage": w.coverage.value, "available": False, "payments": w.n, "total": _num(w.total),
                "reason": "components not disclosed, not verified, or not reconciling for every payment"}
    comps = {c.value.lower(): _num(w.sums[c]) for c in COMP_ORDER if w.sums[c] or c in (ComponentType.INTEREST, ComponentType.CAPITAL_REPAYMENT)}
    shares = {k: (None if not w.total else _num(Decimal(str(v)) / w.total)) for k, v in comps.items()}
    return {"coverage": "COMPLETE", "available": True, "payments": w.n, "total": _num(w.total), "per_unit": comps, "share": shares,
            "income_per_unit": _num(w.class_sum(ComponentClass.INCOME)), "other_per_unit": _num(w.class_sum(ComponentClass.OTHER)),
            "capital_per_unit": _num(w.class_sum(ComponentClass.CAPITAL))}


def _yield_trend(inst, events, price_hist, sources, mode, max_points: int = 60, skip_dates=frozenset()) -> list:
    """Headline TTM yield on each past price date, recomputed server-side. A point is emitted only when its trailing year
    is fully inside the recorded history, every payment is verified-source with an amount, and no cross-source conflict
    touched it; otherwise the point is omitted rather than estimated."""
    if inst.type is InstrumentType.ETF or not price_hist:
        return []
    usable = [e for e in events if e.include and e.total_per_unit is not None]
    if not usable or any(e.amount_grade.value not in ("EXCHANGE", "ISSUER", "REGULATOR") for e in usable):
        return []
    if any((not e.include or e.total_per_unit is None) for e in events if e.status_text.startswith(("DISCREPANCY", "EXCLUDED_DISCREPANCY"))):
        return []
    if any(e.total_per_unit is None for e in events):
        return []
    first = min(e.ex_date for e in usable)
    out = []
    for p, _ in price_hist[-max_points:]:
        if p.date in skip_dates:
            continue                      # a date with an open price discrepancy is never charted
        if mode != "preview":
            s = sources.get(p.source_id)
            if not (s and s.display_cleared):
                continue
        start = p.date - dt.timedelta(days=365)
        if first > start:
            continue
        w = summarize_window(usable, start, p.date)
        if w.n:
            out.append([p.date.isoformat(), _num(w.total / p.price)])
    return out


def dumps(ds: dict) -> str:
    return json.dumps(ds, indent=1, sort_keys=True, allow_nan=False)
