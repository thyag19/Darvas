"use strict";
// Yield Atlas dashboard. Renders data.json only; it computes no financial metrics. Sorting/filtering are user display
// choices, there is no ranking. All text is inserted with textContent (never innerHTML); links are limited to http(s).
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable: app still works */ } },
};
const state = { data: null, type: "ALL", cat: "ALL", q: "", onlyData: false, onlyWatch: false, sortKey: "name", sortDir: 1,
  selected: null, newsFilter: "all", watch: new Set(LS.get("irie.watch", [])), alerts: LS.get("irie.alerts.v2", []),
  soundOn: LS.get("irie.sound", false), refreshFailed: false };
window.__irieSounds = [];

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const NS = "http://www.w3.org/2000/svg";
function s(tag, attrs, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const $ = id => document.getElementById(id);
const pct = v => (v * 100).toFixed(2) + "%";
const num = v => v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
const rupee = v => "₹" + num(v);
const safeUrl = u => /^https?:\/\//i.test(u || "") ? u : null;
const ist = iso => { try { return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) + " IST"; } catch (e) { return iso || "n/a"; } };
const ago = iso => { const m = Math.round((Date.now() - Date.parse(iso)) / 60000); return m < 0 ? "" : m < 60 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
const M = (i, n) => (i.metrics || {})[n];
const mv = (i, n) => { const m = M(i, n); return m && m.value !== null && m.value !== undefined ? m.value : null; };
const premiumMetric = i => M(i, "premium_to_nav") || M(i, "premium_discount_to_nav");
const CAT = { REIT: "REIT", INVIT: "InvIT", INFRASTRUCTURE: "Infrastructure", CORPORATE: "Corporate announcement", OTHER: "Other" };
const humanCat = c => c.replaceAll("_", " ").toLowerCase();

const COLS = [
  { id: "name", label: "Instrument", val: i => i.name, text: true, cls: "name" },
  { id: "type", label: "Type", val: i => i.type, text: true },
  { id: "price", label: "Last price", val: i => i.latest.price && i.latest.price.value, fmt: rupee, cell: i => i.latest.price },
  { id: "ttm_yield", label: "Headline TTM yield", val: i => mv(i, "ttm_yield"), fmt: pct, metric: "ttm_yield" },
  { id: "income_yield", label: "Income yield", val: i => mv(i, "income_yield"), fmt: pct, metric: "income_yield", cls: "hide-sm" },
  { id: "capital_repayment_share", label: "Capital share", val: i => mv(i, "capital_repayment_share"), fmt: pct, metric: "capital_repayment_share", cls: "hide-sm" },
  { id: "premium", label: "Prem. / (disc.) to NAV", val: i => { const m = premiumMetric(i); return m ? m.value : null; }, fmt: pct, metricFn: premiumMetric, cls: "hide-sm" },
  { id: "nav_return_1y", label: "1y NAV return", val: i => mv(i, "nav_return_1y"), fmt: pct, metric: "nav_return_1y", cls: "hide-sm" },
  { id: "observed", label: "Price date", val: i => i.latest.price && i.latest.price.date, text: true, cell: i => i.latest.price, cls: "hide-sm" },
  { id: "flags", label: "Data flags", val: i => flagsOf(i).length, flags: true },
];
function flagsOf(i) {
  const f = new Set();
  for (const m of Object.values(i.metrics || {})) for (const x of m.flags || []) f.add(x);
  if ((i.open_discrepancies || []).length) f.add("SOURCE_DISCREPANCY");
  return [...f].filter(x => !x.startsWith("DEFINITION_") && x !== "IRREGULAR_TRANCHES_DISTORT");
}

function visible() {
  const q = state.q.trim().toLowerCase();
  return state.data.instruments.filter(i =>
    (state.type === "ALL" || i.type === state.type) && (state.cat === "ALL" || i.etf_category === state.cat) &&
    (!q || i.name.toLowerCase().includes(q) || i.key.toLowerCase().includes(q) || (i.isin || "").toLowerCase().includes(q)) &&
    (!state.onlyData || mv(i, "ttm_yield") !== null || mv(i, "trailing_distribution_yield") !== null) &&
    (!state.onlyWatch || state.watch.has(i.key)));
}
function sorted(list) {
  const col = COLS.find(c => c.id === state.sortKey) || COLS[0];
  return [...list].sort((a, b) => {
    const x = col.val(a), y = col.val(b), nx = x === null || x === undefined || x === "", ny = y === null || y === undefined || y === "";
    if (nx && ny) return a.name.localeCompare(b.name);
    if (nx) return 1;               // unavailable values sort last in either direction
    if (ny) return -1;
    const r = typeof x === "string" ? x.localeCompare(y) : x - y;
    return r * state.sortDir || a.name.localeCompare(b.name);
  });
}

// ---------- header, status, cards ----------
function renderStatus() {
  const d = state.data, mk = d.market || { known: false }, hb = $("hours");
  hb.className = "pill " + (mk.known ? (mk.open ? "open" : "closed") : "");
  if (!mk.known) hb.textContent = "Market hours: calendar not loaded";
  else hb.textContent = (mk.open ? "NSE/BSE open" : "NSE/BSE closed" + (mk.holiday ? ` · ${mk.holiday}` : mk.reason === "WEEKEND" ? " · weekend" : "")) + (mk.calendar_verified ? "" : " · calendar unverified");
  hb.title = `Status when this page was generated (${ist(d.generated_at)}). Session ${mk.session || "n/a"}. ` + (mk.next_open ? `Next open ${ist(mk.next_open)}.` : "") + " Prices are only requested during sessions.";
  $("notice").textContent = d.notice; $("notice").className = "notice" + (d.preview ? " preview" : d.synthetic ? " synthetic" : "");
  $("meta").textContent = `Market data as of ${d.as_of} (IST) · generated ${ist(d.generated_at)}` + (state.updated ? ` · page refreshed ${state.updated}` : "");
  const age = (Date.now() - Date.parse(d.generated_at)) / 36e5, w = $("warn");
  const msgs = [];
  if (age > 36 && !d.synthetic) msgs.push(`This page's data was generated ${Math.round(age)} hours ago and may be out of date.`);
  if (state.refreshFailed) msgs.push("Could not refresh just now; showing the last data that loaded.");
  w.hidden = !msgs.length; w.textContent = msgs.join(" ");
}

function renderCards() {
  const list = visible(), all = state.data.instruments, src = state.data.sources, byType = t => all.filter(i => i.type === t).length;
  const fetchable = src.filter(x => x.freshness !== "NOT_FETCHED"), fresh = fetchable.filter(x => x.freshness === "FRESH").length;
  const ylds = t => all.filter(i => i.type === t).map(i => mv(i, "ttm_yield")).filter(v => v !== null);
  const range = t => { const y = ylds(t); return y.length ? (y.length === 1 ? pct(y[0]) : `${pct(Math.min(...y))} – ${pct(Math.max(...y))}`) : "none published"; };
  const cards = [
    ["Instruments", `${list.length} of ${all.length}`, `${byType("INVIT")} InvIT · ${byType("REIT")} REIT · ${byType("ETF")} ETF`],
    ["Published headline yields", all.filter(i => mv(i, "ttm_yield") !== null).length, `InvIT ${range("INVIT")}`],
    ["Yield shown, split unavailable", all.filter(i => mv(i, "ttm_yield") !== null && mv(i, "capital_repayment_share") === null).length, "income vs capital not disclosed or not verified"],
    ["Values withheld", all.reduce((n, i) => n + Object.values(i.metrics).filter(m => m.withheld).length, 0), "source not cleared or blocking flag"],
    ["Open source discrepancies", all.reduce((n, i) => n + (i.open_discrepancies || []).length, 0), "sources disagree; both kept"],
    ["Sources fresh", fetchable.length ? `${fresh} of ${fetchable.length}` : "none fetchable", "judged against the schedule, not the clock"],
  ];
  $("cards").replaceChildren(...cards.map(([l, v, sub]) => h("div", { class: "card", "data-testid": "card" }, h("span", {}, l), h("b", {}, v), h("em", {}, sub))));
}

// ---------- watchlist ----------
function cell(col, i) {
  const c = col.cls || "";
  if (col.id === "name") return h("td", { class: "name" }, h("b", {}, i.name), h("small", { class: "muted" }, i.key + (i.isin ? " · " + i.isin : "")));
  if (col.id === "type") return h("td", {}, h("span", { class: "badge type t-" + i.type }, i.type === "INVIT" ? "InvIT" : i.type), i.etf_category ? h("small", { class: "muted" }, humanCat(i.etf_category)) : null);
  if (col.text) return h("td", { class: c }, col.val(i) ?? "");
  if (col.flags) { const f = flagsOf(i); return h("td", { class: c }, f.length ? f.slice(0, 2).map(x => h("span", { class: "badge bad", title: x }, humanCat(x))).concat(f.length > 2 ? [h("span", { class: "badge", title: f.slice(2).join(", ") }, `+${f.length - 2}`)] : []) : h("span", { class: "badge" }, "none")); }
  const m = col.metricFn ? col.metricFn(i) : col.metric ? M(i, col.metric) : null;
  if (col.cell) { const p = col.cell(i); if (!p) return h("td", { class: "na " + c, title: "no observation" }, "n/a"); if (p.value === null) return h("td", { class: "wh " + c, title: "not cleared for display" }, "withheld"); return h("td", { class: c }, col.fmt(p.value)); }
  if (!m) return h("td", { class: "na " + c, title: "not defined for this instrument" }, "—");
  if (m.value !== null && m.value !== undefined) return h("td", { class: c, title: (m.flags || []).join(", ") }, col.fmt(m.value));
  if (m.withheld) return h("td", { class: "wh " + c, title: (m.withheld_reasons || []).join("; ") }, "withheld");
  return h("td", { class: "na " + c, title: (m.reasons || []).join("; ") || m.status }, "n/a");
}

function renderTable() {
  const head = h("tr", {}, h("th", { scope: "col", title: "Starred" }, "★"), ...COLS.map(c =>
    h("th", { scope: "col", class: c.cls || "", "aria-sort": state.sortKey === c.id ? (state.sortDir > 0 ? "ascending" : "descending") : "none" },
      h("button", { type: "button", "data-testid": "sort-" + c.id, onclick: () => { state.sortDir = state.sortKey === c.id ? -state.sortDir : 1; state.sortKey = c.id; render(); } }, c.label))));
  const rows = sorted(visible());
  $("table").tHead.replaceChildren(head);
  $("table").tBodies[0].replaceChildren(...rows.map(i => {
    const w = state.watch.has(i.key);
    const open = () => openDrawer(i.key);
    return h("tr", { class: state.selected === i.key ? "sel" : "", "data-key": i.key, "data-testid": "row", tabindex: 0, onclick: open, onkeydown: e => { if (e.key === "Enter") open(); } },
      h("td", {}, h("button", { type: "button", class: "star", "data-testid": "star", "aria-pressed": String(w), title: w ? "Remove from starred" : "Star this instrument",
        onclick: e => { e.stopPropagation(); w ? state.watch.delete(i.key) : state.watch.add(i.key); LS.set("irie.watch", [...state.watch]); render(); } }, w ? "★" : "☆")),
      ...COLS.map(c => cell(c, i)));
  }));
  $("count").textContent = `(${rows.length} of ${state.data.instruments.length})`;
  const empty = $("empty"), tw = $("table").parentElement;
  empty.hidden = rows.length > 0; tw.hidden = rows.length === 0;
  if (!rows.length) {
    const total = state.data.instruments.length;
    empty.replaceChildren(h("b", {}, total ? "No instruments match these filters" : "No instruments loaded yet"),
      h("p", {}, total ? "Try a different search, or clear the filters." : "Nothing has been ingested. Instruments appear once an instruments file is supplied through a permitted source."),
      total ? h("button", { type: "button", class: "btn", "data-testid": "clear-filters", onclick: clearFilters }, "Clear filters") : null);
  }
}
function clearFilters() {
  Object.assign(state, { type: "ALL", cat: "ALL", q: "", onlyData: false, onlyWatch: false });
  $("q").value = ""; $("type").value = "ALL"; $("cat").value = "ALL"; $("onlyData").checked = false; $("onlyWatch").checked = false; render();
}

// ---------- charts ----------
const COLORS = { income: "var(--inc)", other: "var(--oth)", capital: "var(--cap)", total: "var(--neutral)" };
function legend() {
  return h("p", { class: "legend" }, ...[["income", "income (interest, dividend, rental)"], ["other", "other income"], ["capital", "capital repayment: returned capital, not income"], ["total", "split unavailable"]]
    .map(([k, l]) => h("span", {}, h("span", { class: "sw", style: "background:" + COLORS[k] }), l)));
}
function barChart(items) {
  const withY = items.filter(i => mv(i, "ttm_yield") !== null);
  if (!withY.length) return h("div", {}, h("p", { "data-testid": "no-yield" }, h("b", {}, "No published yields for the current selection.")),
    h("p", { class: "note" }, "Yields appear when a source is cleared for display and the figure carries no blocking data-quality flag."));
  const groups = {}; withY.forEach(i => (groups[i.type] = groups[i.type] || []).push(i));
  const out = [h("p", { class: "note" }, "Yield definitions differ by instrument type, so bars are grouped by type and never mixed."), legend()];
  const max = Math.max(...withY.map(i => mv(i, "ttm_yield")));
  for (const [type, list] of Object.entries(groups)) {
    const W = 560, rowH = 28, labelW = 200, H = list.length * rowH + 8;
    const svg = s("svg", { width: "100%", viewBox: `0 0 ${W + labelW + 70} ${H}`, role: "img", "aria-label": `${type} headline yields`, "data-testid": "bars-" + type });
    list.forEach((i, n) => {
      const y = n * rowH + 4, total = mv(i, "ttm_yield"), inc = mv(i, "income_yield"), oth = mv(i, "other_yield"), cap = mv(i, "capital_repayment_yield"), sc = v => (v / max) * W;
      svg.append(s("text", { x: 0, y: y + 14 }, i.name.length > 32 ? i.name.slice(0, 31) + "…" : i.name));
      if (inc !== null && oth !== null && cap !== null) { let x = labelW; for (const [v, c] of [[inc, COLORS.income], [oth, COLORS.other], [cap, COLORS.capital]]) { svg.append(s("rect", { x, y, width: Math.max(sc(v), 0), height: 18, fill: c }, s("title", {}, pct(v)))); x += sc(v); } }
      else svg.append(s("rect", { x: labelW, y, width: sc(total), height: 18, fill: COLORS.total }));
      svg.append(s("text", { x: labelW + sc(total) + 6, y: y + 14 }, pct(total)));
    });
    out.push(h("h3", {}, type === "INVIT" ? "InvITs" : type === "REIT" ? "REITs" : "ETFs"), svg);
  }
  return h("div", {}, out);
}
function lineChart(points, label, unit) {
  if (points.length < 2) return h("p", { class: "note" }, `${label}: no history available${points.length ? " (one observation)" : ""}.`);
  const W = 600, H = 170, P = 44, xs = points.map(p => Date.parse(p[0])), ys = points.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), dy = y1 - y0 || 1;
  const X = t => P + ((t - x0) / (x1 - x0 || 1)) * (W - P - 10), Y = v => H - 26 - ((v - y0) / dy) * (H - 40);
  return h("div", {}, h("p", { class: "note" }, label), s("svg", { width: "100%", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label },
    s("polyline", { fill: "none", stroke: "var(--accent)", "stroke-width": 2, points: points.map(p => `${X(Date.parse(p[0]))},${Y(p[1])}`).join(" ") }),
    s("text", { x: 2, y: 14, class: "axis" }, unit === "%" ? pct(y1) : num(y1)), s("text", { x: 2, y: H - 26, class: "axis" }, unit === "%" ? pct(y0) : num(y0)),
    s("text", { x: P, y: H - 8, class: "axis" }, points[0][0]), s("text", { x: W - 76, y: H - 8, class: "axis" }, points[points.length - 1][0])));
}
function priceYieldChart(prices, trend) {
  if (prices.length < 2) return lineChart(prices, "Price history (₹)", "");
  if (trend.length < 2) return h("div", {}, lineChart(prices, "Price history (₹)", ""), h("p", { class: "note" }, "Headline yield trend: not shown. It needs a full trailing year of verified distributions inside the recorded history."));
  const W = 600, H = 190, P = 46, R = 50, all = prices.map(p => Date.parse(p[0])).concat(trend.map(p => Date.parse(p[0])));
  const x0 = Math.min(...all), x1 = Math.max(...all), X = t => P + ((t - x0) / (x1 - x0 || 1)) * (W - P - R);
  const scale = pts => { const v = pts.map(p => p[1]), lo = Math.min(...v), hi = Math.max(...v), d = hi - lo || 1; return [lo, hi, y => H - 28 - ((y - lo) / d) * (H - 44)]; };
  const [pl, ph, PY] = scale(prices), [yl, yh, YY] = scale(trend);
  return h("div", {}, h("p", { class: "legend" }, h("span", {}, h("span", { class: "sw", style: "background:var(--accent)" }), "Last price (₹, left axis)"), h("span", {}, h("span", { class: "sw", style: "background:var(--oth)" }), "Headline TTM yield (right axis)")),
    s("svg", { width: "100%", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Price and headline TTM yield history", "data-testid": "trend-chart" },
      s("polyline", { fill: "none", stroke: "var(--accent)", "stroke-width": 2, points: prices.map(p => `${X(Date.parse(p[0]))},${PY(p[1])}`).join(" ") }),
      s("polyline", { fill: "none", stroke: "var(--oth)", "stroke-width": 2, "stroke-dasharray": "5 3", points: trend.map(p => `${X(Date.parse(p[0]))},${YY(p[1])}`).join(" ") }),
      s("text", { x: 2, y: 14, class: "axis" }, num(ph)), s("text", { x: 2, y: H - 28, class: "axis" }, num(pl)),
      s("text", { x: W - R + 6, y: 14, class: "axis" }, pct(yh)), s("text", { x: W - R + 6, y: H - 28, class: "axis" }, pct(yl)),
      s("text", { x: P, y: H - 8, class: "axis" }, new Date(x0).toISOString().slice(0, 10)), s("text", { x: W - R - 70, y: H - 8, class: "axis" }, new Date(x1).toISOString().slice(0, 10))));
}
function distChart(hist) {
  if (!hist.length) return h("p", { class: "note" }, "No published distribution history.");
  const W = 600, H = 180, P = 34, max = Math.max(...hist.map(d => d.total)), bw = Math.max(6, (W - P) / hist.length - 4);
  const svg = s("svg", { width: "100%", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Distribution per payment", "data-testid": "dist-chart" });
  hist.forEach((d, n) => {
    const x = P + n * ((W - P) / hist.length), sc = v => (v / max) * (H - 44); let y = H - 24;
    const parts = d.split ? [[d.split.income, COLORS.income], [d.split.other, COLORS.other], [d.split.capital, COLORS.capital]] : [[d.total, COLORS.total]];
    for (const [v, c] of parts) { y -= sc(v); svg.append(s("rect", { x, y, width: bw, height: sc(v), fill: c }, s("title", {}, `${d.ex_date}: ${num(v)} per unit`))); }
    if (n % Math.ceil(hist.length / 6) === 0) svg.append(s("text", { x, y: H - 8, class: "axis" }, d.ex_date.slice(0, 7)));
  });
  svg.append(s("text", { x: 0, y: 12, class: "axis" }, num(max)));
  return h("div", {}, legend(), svg);
}

// ---------- detail drawer ----------
const COMP_LABEL = { interest: "Interest income", dividend: "Dividend income", rental: "Rental income", other_income: "Other income", capital_repayment: "Return of capital" };
function kpi(label, i, name, fmt, fn) {
  const m = fn ? fn(i) : M(i, name);
  let v = "—", cls = "na", t = "";
  if (m) { if (m.value !== null && m.value !== undefined) { v = fmt(m.value); cls = ""; t = (m.flags || []).join(", "); } else if (m.withheld) { v = "withheld"; cls = "wh"; t = (m.withheld_reasons || []).join("; "); } else { v = "n/a"; t = (m.reasons || []).join("; "); } }
  return h("div", { class: "kpi", title: t }, h("span", {}, label), h("b", { class: cls }, v));
}
function breakdownView(i) {
  const b = i.breakdown;
  if (b === null || b === undefined) return null;
  if (!b.available) return h("div", {}, h("h3", {}, "Distribution components (trailing 12 months)"), h("p", { class: "note", "data-testid": "breakdown-na" }, `Not available: ${b.reason}. No split is estimated or inferred. Coverage: ${humanCat(b.coverage)}.`));
  const order = ["interest", "dividend", "rental", "other_income", "capital_repayment"].filter(k => k in b.per_unit);
  return h("div", {}, h("h3", {}, `Distribution components, trailing 12 months (${b.payments} payments, ${rupee(b.total)} per unit)`),
    h("div", { class: "comps", "data-testid": "breakdown" }, order.map(k => {
      const share = b.share[k], capital = k === "capital_repayment";
      return h("div", { class: "comp" + (capital ? " cap" : ""), "data-testid": "comp-" + k }, h("small", { class: "muted" }, COMP_LABEL[k]), h("b", {}, rupee(b.per_unit[k]) + " / unit"),
        h("small", {}, share === null ? "" : pct(share) + " of distributions"), capital ? h("small", { class: "muted" }, "Returned capital, not income") : null,
        h("div", { class: "bar" }, h("i", { style: `width:${Math.min(100, (share || 0) * 100)}%;background:${capital ? COLORS.capital : k === "other_income" ? COLORS.other : COLORS.income}` })));
    })));
}
function openDrawer(key) {
  state.selected = key; renderDrawer(); renderTable();
  const d = $("drawer"); if (!d.open) d.showModal();
}
function renderDrawer() {
  const i = state.data.instruments.find(x => x.key === state.selected), d = $("drawer");
  if (!i) { if (d.open) d.close(); return; }
  const isEtf = i.type === "ETF";
  const rows = Object.entries(i.metrics).map(([n, m]) => h("tr", {}, h("td", {}, n), h("td", {}, m.value !== null && m.value !== undefined ? (m.unit === "ratio" ? pct(m.value) : num(m.value)) : (m.withheld ? "withheld" : "n/a")),
    h("td", {}, m.status), h("td", {}, (m.flags || []).join(", ")), h("td", {}, (m.reasons || m.withheld_reasons || []).join("; ")), h("td", {}, (m.sources || []).join(", "))));
  const related = state.data.news.items.filter(n => n.instrument_key === i.key).slice(0, 3);
  d.replaceChildren(
    h("div", { class: "dhead" }, h("div", {}, h("h2", {}, i.name), h("div", {}, h("span", { class: "badge type t-" + i.type }, i.type === "INVIT" ? "InvIT" : i.type), i.etf_category ? h("span", { class: "badge" }, humanCat(i.etf_category)) : null, h("span", { class: "badge" }, i.key), i.isin ? h("span", { class: "badge" }, "ISIN " + i.isin) : null)),
      h("button", { type: "button", class: "btn icon", "aria-label": "Close detail", "data-testid": "drawer-close", onclick: () => d.close() }, "✕")),
    h("div", { class: "dbody" },
      h("div", { class: "kpis" }, kpi("Last price", i, null, rupee, () => { const p = i.latest.price; return p ? { value: p.value, withheld: p.value === null, withheld_reasons: ["not cleared for display"] } : null; }),
        isEtf ? [kpi("Premium / (discount)", i, null, pct, premiumMetric), kpi("1y NAV return", i, "nav_return_1y", pct), kpi("Top-10 weight", i, "holdings_top10_weight", pct)]
          : [kpi("Headline TTM yield", i, "ttm_yield", pct), kpi("Income yield", i, "income_yield", pct), kpi("Premium / (discount) to NAV", i, null, pct, premiumMetric)]),
      isEtf ? lineChart(i.history.navs, "NAV history (₹)", "") : [h("h3", {}, "Price and headline yield"), priceYieldChart(i.history.prices, i.history.yield_trend)],
      isEtf ? lineChart(i.history.prices, "Price history (₹)", "") : null,
      isEtf ? null : [h("h3", {}, "Distribution per payment"), distChart(i.history.distributions)],
      breakdownView(i),
      isEtf && i.holdings.length ? h("div", {}, h("h3", {}, `Top holdings (portfolio as of ${i.holdings[0].as_of})`), h("div", { class: "tablewrap" }, h("table", { "data-testid": "holdings", style: "min-width:0" }, h("tbody", {}, i.holdings.map(x => h("tr", {}, h("td", {}, x.name), h("td", {}, x.isin), h("td", {}, pct(x.weight)))))))) : null,
      isEtf && !i.holdings.length ? h("p", { class: "note" }, "Holdings: not available for this instrument (not disclosed in a supplied source, or not published).") : null,
      i.latest.price ? h("p", { class: "note" }, `Latest price observed ${i.latest.price.date} (${i.latest.price.venue || "venue n/a"}); retrieved ${ist(i.latest.price.retrieved_at)}; source ${i.latest.price.source}.`) : null,
      i.latest.nav ? h("p", { class: "note" }, `Latest NAV as of ${i.latest.nav.date} (${i.latest.nav.grade}); retrieved ${ist(i.latest.nav.retrieved_at)}; source ${i.latest.nav.source}.`) : null,
      (i.open_discrepancies || []).length ? h("p", { class: "badge bad", "data-testid": "discrepancy" }, "Open source discrepancy: " + i.open_discrepancies.map(x => `${x.field} ${x.date} (${x.a} vs ${x.b})`).join("; ")) : null,
      related.length ? h("div", {}, h("h3", {}, "Related announcements"), related.map(newsItem)) : null,
      h("h3", {}, "Metrics, status and flags"), h("div", { class: "tablewrap" }, h("table", { style: "min-width:0" }, h("thead", {}, h("tr", {}, ...["Metric", "Value", "Status", "Flags", "Reasons", "Sources"].map(x => h("th", { scope: "col" }, x)))), h("tbody", {}, rows)))));
}

// ---------- news ----------
const NEWS_FILTERS = { all: () => true, reit: n => n.category === "REIT", invit: n => n.category === "INVIT" || n.category === "INFRASTRUCTURE", corp: n => n.category === "CORPORATE" };
function newsItem(n) {
  const url = safeUrl(n.url);
  return h("article", { class: "news", "data-testid": "news-item" },
    h("div", {}, h("div", { class: "chips" }, h("span", { class: "badge type" }, CAT[n.category] || n.category), n.instrument_key ? h("span", { class: "badge" }, n.instrument_key) : null, n.synthetic ? h("span", { class: "badge syn" }, "SYNTHETIC") : null),
      h("h4", {}, n.headline), n.summary ? h("p", {}, n.summary) : null,
      h("div", { class: "when" }, `${n.publisher || n.source_name} · published ${ist(n.published_at)} ${ago(n.published_at) ? "(" + ago(n.published_at) + ")" : ""} · source ${n.source_name}`)),
    url ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, "Open original ↗") : h("span", { class: "muted" }, "no link"));
}
function renderNews() {
  const nw = state.data.news, items = nw.items.filter(NEWS_FILTERS[state.newsFilter]);
  document.querySelectorAll("#news .seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.f === state.newsFilter)));
  if (items.length) { $("newslist").replaceChildren(...items.map(newsItem)); return; }
  let why;
  if (nw.items.length) why = "No items in this category.";
  else if (nw.withheld) why = `${nw.withheld} item(s) exist but their source is not cleared for display, so they are withheld.`;
  else if (!nw.feed_connected) why = "No announcements source is connected. Every external announcements source is currently not cleared for automated retrieval, so nothing is fetched. Items appear when you supply news files through a permitted route or a source is cleared.";
  else why = "A source is connected but has supplied no announcements yet.";
  $("newslist").replaceChildren(h("div", { class: "empty", "data-testid": "news-empty" }, h("b", {}, "No announcements to show"), h("p", {}, why)));
}

// ---------- sources ----------
const SCHED = s => ({ local: "Local files, hourly", market_hours: "Hourly in NSE/BSE sessions", daily: "Daily, off-hours", market_and_daily: "Hourly in sessions + daily off-hours" })[s] || s;
function renderSources() {
  $("srcTable").replaceChildren(h("thead", {}, h("tr", {}, ...["Source", "Grade", "Access", "Display cleared", "Schedule", "Next attempt", "Freshness", "Last attempt", "Last attempt status", "Last success", "Observed through", "Failures"].map(x => h("th", { scope: "col" }, x)))),
    h("tbody", {}, state.data.sources.map(x => h("tr", { "data-testid": "source-row" }, h("td", {}, x.terms_url ? h("a", { href: safeUrl(x.terms_url) || "#", rel: "noopener noreferrer" }, x.name) : x.name, x.synthetic ? h("span", { class: "badge syn" }, "SYNTHETIC") : null),
      h("td", {}, x.grade), h("td", {}, x.access.replace("_", " ").toLowerCase()), h("td", {}, x.display_cleared ? "yes" : "no"), h("td", {}, SCHED(x.schedule)), h("td", {}, x.next_attempt_at ? ist(x.next_attempt_at) : "not scheduled"),
      h("td", {}, h("span", { class: "badge " + (x.freshness === "STALE" || x.freshness === "NEVER" ? "bad" : "") }, x.freshness.replace("_", " ").toLowerCase())),
      h("td", {}, x.last_attempt_at ? ist(x.last_attempt_at) : "never"), h("td", {}, (x.last_attempt_status || "—").replaceAll("_", " ").toLowerCase()), h("td", {}, x.last_success_at ? ist(x.last_success_at) : "never"), h("td", {}, x.observed_through || "—"), h("td", {}, x.consecutive_failures)))));
}

// ---------- alerts ----------
const ALERT_RULES = {
  yield_above: { metric: "ttm_yield", test: (v, t) => v * 100 > t, fmt: v => (v * 100).toFixed(2) + "%" },
  yield_below: { metric: "ttm_yield", test: (v, t) => v * 100 < t, fmt: v => (v * 100).toFixed(2) + "%" },
  premium_above: { metric: "premium", test: (v, t) => v * 100 > t, fmt: v => (v * 100).toFixed(2) + "%" },
  discount_below: { metric: "premium", test: (v, t) => v * 100 < t, fmt: v => (v * 100).toFixed(2) + "%" },
  capital_share_above: { metric: "capital_repayment_share", test: (v, t) => v * 100 > t, fmt: v => (v * 100).toFixed(2) + "%" },
  price_above: { metric: "price", test: (v, t) => v > t, fmt: rupee },
  price_below: { metric: "price", test: (v, t) => v < t, fmt: rupee },
};
const BLOCK = ["UNVERIFIED_SOURCE", "PRICE_STALE", "NAV_STALE", "NAV_UNVERIFIED", "SOURCE_DISCREPANCY", "AMOUNT_UNAVAILABLE_IN_WINDOW", "COMPONENTS_DO_NOT_RECONCILE"];
function reliable(i, metric) {
  if (metric === "price") { const p = i.latest.price; if (!p || p.value === null) return null; const age = (Date.parse(state.data.as_of) - Date.parse(p.date)) / 864e5; return age <= 3 ? p.value : null; }
  const m = metric === "premium" ? premiumMetric(i) : M(i, metric);
  if (!m || m.value === null || m.value === undefined || !m.publishable || (m.flags || []).some(f => BLOCK.includes(f))) return null;
  return m.value;
}
function alertLabel(a) { const t = state.data.alert_types.find(x => x.id === a.type); return `${t ? t.label : a.type} ${a.value}`; }
function evalAlerts(first) {
  let changed = false;
  for (const a of state.alerts) {
    if (a.state === "TRIGGERED") continue;
    const targets = a.key === "*" ? state.data.instruments : state.data.instruments.filter(i => i.key === a.key);
    if (a.type === "data_stale") {   // about OUR retrieval time, so it needs no figure to be reliable
      for (const i of targets) {
        const p = i.latest.price, hrs = p && p.retrieved_at ? (Date.now() - Date.parse(p.retrieved_at)) / 36e5 : null;
        if (hrs !== null && hrs > a.value) {
          Object.assign(a, { state: "TRIGGERED", triggered_at: new Date().toISOString(), triggered_value: `${hrs.toFixed(1)} h old`, triggered_name: i.name });
          changed = true; toast(`Alert: ${i.name}: price data ${hrs.toFixed(1)} h old`); playSound(a.sound);
          break;
        }
      }
      continue;
    }
    const rule = ALERT_RULES[a.type];
    if (!rule) continue;
    for (const i of targets) {
      const v = reliable(i, rule.metric);
      if (v !== null && rule.test(v, a.value)) {
        Object.assign(a, { state: "TRIGGERED", triggered_at: new Date().toISOString(), triggered_value: rule.fmt(v), triggered_name: i.name });
        changed = true; toast(`Alert: ${i.name}: ${alertLabel(a)} (now ${rule.fmt(v)})`); playSound(a.sound);
        break;
      }
    }
  }
  if (changed) LS.set("irie.alerts.v2", state.alerts);
  renderAlertBanner();
  if ($("alertModal").open) renderAlertList();      // keep the open Alert Center in step with a just-triggered alert
}
function renderAlertBanner() {
  const trig = state.alerts.filter(a => a.state === "TRIGGERED");
  $("alerts").replaceChildren(...trig.map(a => h("div", { class: "alert", "data-testid": "alert-hit" }, `${a.triggered_name || "Instrument"}: ${alertLabel(a)} (now ${a.triggered_value}) · triggered ${ist(a.triggered_at)}`)));
  const b = $("alertBadge"); b.hidden = !trig.length; b.textContent = trig.length;
}
function renderAlertList() {
  $("alertCount").textContent = `${state.alerts.length} saved · ${state.alerts.filter(a => a.state === "TRIGGERED").length} triggered`;
  $("alertlist").replaceChildren(...(state.alerts.length ? state.alerts.map(a => {
    const trig = a.state === "TRIGGERED", inst = a.key === "*" ? "All instruments" : (state.data.instruments.find(i => i.key === a.key) || { name: a.key }).name;
    return h("li", { class: trig ? "trig" : "", "data-testid": "alert-item" },
      h("div", { class: "row" }, h("b", {}, `${inst}: ${alertLabel(a)}`), h("span", { class: "badge " + (trig ? "bad" : ""), "data-testid": "alert-state" }, trig ? "TRIGGERED" : "ACTIVE")),
      h("small", { class: "muted" }, `Created ${ist(a.created_at)} · sound: ${a.sound === "none" ? "silent" : a.sound}` + (trig ? ` · triggered ${ist(a.triggered_at)} at ${a.triggered_value}` : "")),
      h("div", { class: "row" }, h("span", {}), h("span", {}, trig ? h("button", { type: "button", class: "btn small", "data-testid": "alert-rearm", onclick: () => { a.state = "ACTIVE"; delete a.triggered_at; LS.set("irie.alerts.v2", state.alerts); renderAlertList(); evalAlerts(); } }, "Re-arm") : null,
        " ", h("button", { type: "button", class: "btn small", "data-testid": "alert-delete", onclick: () => { state.alerts.splice(state.alerts.indexOf(a), 1); LS.set("irie.alerts.v2", state.alerts); renderAlertList(); renderAlertBanner(); } }, "Delete"))));
  }) : [h("li", { "data-testid": "alert-empty" }, h("b", {}, "No alerts yet"), h("small", { class: "muted" }, "Choose an instrument, a trigger and a threshold above. Alerts are stored in this browser only.")) ]));
}
let audio = null;
function playSound(kind) {
  if (!state.soundOn || kind === "none") return;
  window.__irieSounds.push({ kind, at: Date.now() });
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const tones = { chime: [[880, 0, .25], [1320, .18, .35]], beep: [[800, 0, .3]], tick: [[1000, 0, .08], [1000, .16, .08]] }[kind] || [];
    for (const [f, t, d] of tones) { const o = audio.createOscillator(), g = audio.createGain(); o.frequency.value = f; g.gain.setValueAtTime(.15, audio.currentTime + t); g.gain.exponentialRampToValueAtTime(.001, audio.currentTime + t + d); o.connect(g); g.connect(audio.destination); o.start(audio.currentTime + t); o.stop(audio.currentTime + t + d + .02); }
  } catch (e) { /* no audio device: the visual alert still shows */ }
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => { t.hidden = true; }, 6000); }

// ---------- csv ----------
function csv() {
  const d = state.data, list = sorted(visible());
  const names = [...new Set(d.instruments.flatMap(i => Object.keys(i.metrics)))].sort();
  const q = v => { v = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replaceAll('"', '""') + '"' : v; };
  const head = ["key", "name", "type", "etf_category", "isin", "price", "price_date", "price_source", "price_retrieved_at", ...names.flatMap(n => [n, n + "_status", n + "_flags"])];
  const lines = [`# as_of ${d.as_of}; generated_at ${d.generated_at}; mode ${d.mode}`, `# ${d.notice}`, "# Blank value = unavailable or withheld, never zero. Ratios are fractions (0.05 = 5%).", head.join(",")];
  for (const i of list) {
    const p = i.latest.price || {};
    lines.push([i.key, i.name, i.type, i.etf_category, i.isin, p.value, p.date, p.source, p.retrieved_at,
      ...names.flatMap(n => { const m = i.metrics[n]; return m ? [m.value, m.status + (m.withheld ? " (withheld)" : ""), (m.flags || []).join("|")] : ["", "NOT_APPLICABLE", ""]; })].map(q).join(","));
  }
  const a = h("a", { href: URL.createObjectURL(new Blob([lines.join("\n") + "\n"], { type: "text/csv" })), download: `instruments_${d.as_of}.csv` });
  document.body.append(a); a.click(); a.remove();
}

function render() {
  try {
    renderStatus(); renderCards(); renderTable(); $("yieldchart").replaceChildren(barChart(visible())); renderNews(); renderSources(); renderAlertBanner();
    if ($("drawer").open) renderDrawer();
    if ($("alertModal").open) renderAlertList();
  } catch (e) {
    console.error(e);
    $("notice").textContent = "Something went wrong while drawing the page. Reload to try again.";
  }
}

function fail(msg) {
  document.querySelector("main").replaceChildren(h("div", { class: "err", "data-testid": "load-error" }, h("h2", {}, "Data could not be loaded"),
    h("p", {}, msg), h("button", { type: "button", class: "btn primary", onclick: () => location.reload() }, "Retry")));
  $("notice").textContent = "Could not load data.json. The dashboard needs it to render.";
}
async function load() {
  const r = await fetch("data.json", { cache: "no-cache" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  const d = await r.json();
  if (!d || !Array.isArray(d.instruments) || !d.news || !d.sources) throw new Error("unexpected data format");
  return d;
}
async function refresh() {
  try { state.data = await load(); state.refreshFailed = false; state.updated = new Date().toLocaleTimeString("en-IN", { hour12: false }); }
  catch (e) { state.refreshFailed = true; }
  if (state.data) { render(); evalAlerts(); }
}

function setTheme(t) { if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme"); }
async function init() {
  setTheme(LS.get("irie.theme", null));
  $("theme").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const nxt = cur === "dark" ? "light" : "dark"; setTheme(nxt); LS.set("irie.theme", nxt);
  });
  try { state.data = await load(); } catch (e) { fail("The data file is missing or unreadable (" + e.message + ")."); return; }
  const d = state.data;
  const cats = [...new Set(d.instruments.map(i => i.etf_category).filter(Boolean))].sort();
  $("cat").replaceChildren(h("option", { value: "ALL" }, "All categories"), ...cats.map(c => h("option", { value: c }, humanCat(c))));
  $("atype").replaceChildren(...d.alert_types.map(t => h("option", { value: t.id }, t.label)));
  $("ainst").replaceChildren(h("option", { value: "*" }, "All instruments"), ...d.instruments.map(i => h("option", { value: i.key }, i.name)));
  $("q").addEventListener("input", e => { state.q = e.target.value; render(); });
  $("type").addEventListener("change", e => { state.type = e.target.value; render(); });
  $("cat").addEventListener("change", e => { state.cat = e.target.value; render(); });
  $("onlyData").addEventListener("change", e => { state.onlyData = e.target.checked; render(); });
  $("onlyWatch").addEventListener("change", e => { state.onlyWatch = e.target.checked; render(); });
  $("csv").addEventListener("click", csv);
  document.querySelectorAll("#news .seg button").forEach(b => b.addEventListener("click", () => { state.newsFilter = b.dataset.f; renderNews(); }));
  $("openAlerts").addEventListener("click", () => { renderAlertList(); $("soundOn").checked = state.soundOn; $("alertModal").showModal(); });
  $("closeAlerts").addEventListener("click", () => $("alertModal").close());
  for (const dlg of [$("drawer"), $("alertModal")]) dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });
  $("drawer").addEventListener("close", () => { state.selected = null; renderTable(); });
  $("soundOn").addEventListener("change", e => { state.soundOn = e.target.checked; LS.set("irie.sound", state.soundOn); if (state.soundOn) playSound("chime"); });
  $("testSound").addEventListener("click", () => { const was = state.soundOn; state.soundOn = true; playSound($("asound").value === "none" ? "chime" : $("asound").value); state.soundOn = was; });
  $("alertform").addEventListener("submit", e => {
    e.preventDefault();
    const v = parseFloat($("aval").value);
    if (!isFinite(v)) return;
    state.alerts.push({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), type: $("atype").value, key: $("ainst").value, value: v, sound: $("asound").value,
      created_at: new Date().toISOString(), state: "ACTIVE" });
    LS.set("irie.alerts.v2", state.alerts); $("aval").value = ""; renderAlertList(); evalAlerts();
  });
  render(); evalAlerts(true);
  window.irieRefresh = refresh;     // also lets tests exercise the refresh-failure path
  setInterval(refresh, 5 * 60 * 1000);
}
init();
