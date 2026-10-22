"use strict";
// Dashboard: renders data.json only. It computes no financial metrics; sorting/filtering are user display choices.
const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable: still works */ } },
};
const state = { data: null, type: "ALL", cat: "ALL", q: "", onlyData: false, onlyWatch: false,
  sortKey: "name", sortDir: 1, selected: null, watch: new Set(LS.get("irie.watch", [])), alerts: LS.get("irie.alerts", []) };

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const svgNS = "http://www.w3.org/2000/svg";
function s(tag, attrs, ...kids) {
  const e = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const pct = v => (v * 100).toFixed(2) + "%";
const num = v => v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
const $ = id => document.getElementById(id);
const M = (i, n) => (i.metrics || {})[n];
const premiumMetric = i => M(i, "premium_to_nav") || M(i, "premium_discount_to_nav");

const COLS = [
  { id: "name", label: "Instrument", val: i => i.name, text: true },
  { id: "type", label: "Type", val: i => i.type + (i.etf_category ? " / " + i.etf_category.replaceAll("_", " ").toLowerCase() : ""), text: true },
  { id: "price", label: "Price (₹)", val: i => i.latest.price && i.latest.price.value, fmt: num, cell: i => i.latest.price },
  { id: "ttm_yield", label: "Headline TTM yield", val: i => mv(i, "ttm_yield"), fmt: pct, metric: "ttm_yield" },
  { id: "income_yield", label: "Income yield", val: i => mv(i, "income_yield"), fmt: pct, metric: "income_yield" },
  { id: "capital_repayment_share", label: "Capital-repayment share", val: i => mv(i, "capital_repayment_share"), fmt: pct, metric: "capital_repayment_share" },
  { id: "premium", label: "Premium / (discount) to NAV", val: i => { const m = premiumMetric(i); return m ? m.value : null; }, fmt: pct, metricFn: premiumMetric },
  { id: "nav_return_1y", label: "1y NAV return", val: i => mv(i, "nav_return_1y"), fmt: pct, metric: "nav_return_1y" },
  { id: "observed", label: "Price date", val: i => i.latest.price && i.latest.price.date, text: true, cell: i => i.latest.price },
  { id: "flags", label: "Data flags", val: i => flagsOf(i).length, flags: true },
];
function mv(i, n) { const m = M(i, n); return m && m.value !== null && m.value !== undefined ? m.value : null; }
function flagsOf(i) {
  const f = new Set();
  for (const m of Object.values(i.metrics || {})) for (const x of m.flags || []) f.add(x);
  if ((i.open_discrepancies || []).length) f.add("SOURCE_DISCREPANCY");
  return [...f].filter(x => !x.startsWith("DEFINITION_"));
}

function visible() {
  const q = state.q.trim().toLowerCase();
  return state.data.instruments.filter(i =>
    (state.type === "ALL" || i.type === state.type) &&
    (state.cat === "ALL" || i.etf_category === state.cat) &&
    (!q || i.name.toLowerCase().includes(q) || i.key.toLowerCase().includes(q) || (i.isin || "").toLowerCase().includes(q)) &&
    (!state.onlyData || mv(i, "ttm_yield") !== null || mv(i, "trailing_distribution_yield") !== null) &&
    (!state.onlyWatch || state.watch.has(i.key)));
}
function sorted(list) {
  const col = COLS.find(c => c.id === state.sortKey) || COLS[0];
  return [...list].sort((a, b) => {
    const x = col.val(a), y = col.val(b);
    if ((x === null || x === undefined) && (y === null || y === undefined)) return a.name.localeCompare(b.name);
    if (x === null || x === undefined) return 1;    // unavailable values sort last in either direction
    if (y === null || y === undefined) return -1;
    const r = typeof x === "string" ? x.localeCompare(y) : x - y;
    return r * state.sortDir || a.name.localeCompare(b.name);
  });
}

function cell(col, i) {
  if (col.text) return h("td", {}, col.val(i) ?? "");
  if (col.flags) { const f = flagsOf(i); return h("td", {}, f.length ? f.slice(0, 3).map(x => h("span", { class: "badge bad", title: x }, x.replaceAll("_", " ").toLowerCase())) : h("span", { class: "badge ok" }, "none")); }
  const m = col.metricFn ? col.metricFn(i) : col.metric ? M(i, col.metric) : null;
  if (col.cell) { const c = col.cell(i); if (!c) return h("td", { class: "na", title: "no observation" }, "n/a"); if (c.value === null) return h("td", { class: "wh", title: "not cleared for display" }, "withheld"); return h("td", {}, col.fmt(c.value)); }
  if (!m) return h("td", { class: "na", title: "not defined for this instrument" }, "—");
  if (m.value !== null && m.value !== undefined) return h("td", { title: (m.flags || []).join(", ") }, col.fmt(m.value));
  if (m.withheld) return h("td", { class: "wh", title: (m.withheld_reasons || []).join("; ") }, "withheld");
  return h("td", { class: "na", title: (m.reasons || []).join("; ") || m.status }, "n/a");
}

function renderTable() {
  const head = h("tr", {}, h("th", { scope: "col", title: "Watchlist" }, "★"), ...COLS.map(c =>
    h("th", { scope: "col", "aria-sort": state.sortKey === c.id ? (state.sortDir > 0 ? "ascending" : "descending") : "none" },
      h("button", { type: "button", "data-testid": "sort-" + c.id, onclick: () => { state.sortDir = state.sortKey === c.id ? -state.sortDir : 1; state.sortKey = c.id; render(); } }, c.label))));
  const rows = sorted(visible());
  $("table").tHead.replaceChildren(head);
  $("table").tBodies[0].replaceChildren(...rows.map(i => {
    const w = state.watch.has(i.key);
    return h("tr", { class: state.selected === i.key ? "sel" : "", "data-key": i.key, "data-testid": "row", tabindex: 0,
      onclick: () => { state.selected = i.key; render(); }, onkeydown: e => { if (e.key === "Enter") { state.selected = i.key; render(); } } },
      h("td", {}, h("button", { type: "button", class: "star", "data-testid": "star", "aria-pressed": String(w), title: w ? "Remove from watchlist" : "Add to watchlist",
        onclick: e => { e.stopPropagation(); w ? state.watch.delete(i.key) : state.watch.add(i.key); LS.set("irie.watch", [...state.watch]); render(); } }, w ? "★" : "☆")),
      ...COLS.map(c => cell(c, i)));
  }));
  $("count").textContent = `(${rows.length} of ${state.data.instruments.length})`;
}

function renderCards() {
  const list = visible(), all = state.data.instruments, src = state.data.sources;
  const fetchable = src.filter(x => x.freshness !== "NOT_FETCHED");
  const lastOk = src.map(x => x.last_success_at).filter(Boolean).sort().pop();
  const cards = [
    ["Instruments shown", `${list.length} / ${all.length}`],
    ["With a published headline yield", list.filter(i => mv(i, "ttm_yield") !== null).length],
    ["Yield shown without income/capital split", list.filter(i => mv(i, "ttm_yield") !== null && mv(i, "capital_repayment_share") === null).length],
    ["Values withheld", list.reduce((n, i) => n + Object.values(i.metrics).filter(m => m.withheld).length, 0)],
    ["Open source discrepancies", all.reduce((n, i) => n + (i.open_discrepancies || []).length, 0)],
    ["Sources retrieved / fetchable", `${fetchable.filter(x => x.freshness === "FRESH").length} fresh of ${fetchable.length}`],
    ["Last successful retrieval", lastOk ? lastOk.replace("T", " ").replace("Z", " UTC") : "never"],
  ];
  $("cards").replaceChildren(...cards.map(([l, v]) => h("div", { class: "card", "data-testid": "card" }, h("b", {}, v), h("span", {}, l))));
}

function barChart(items) {
  const withY = items.filter(i => mv(i, "ttm_yield") !== null);
  if (!withY.length) return h("p", { class: "note", "data-testid": "no-yield" }, "No published yields for the current selection.");
  const groups = {};
  withY.forEach(i => (groups[i.type] = groups[i.type] || []).push(i));
  const out = [h("p", { class: "note" }, "Yield definitions differ by instrument type, so bars are grouped by type. Blue = income, amber = other income, red = capital repayment (returned capital, not income), grey = split unavailable."),
    h("p", { class: "legend" }, ...[["var(--inc)", "income"], ["var(--oth)", "other"], ["var(--cap)", "capital repayment"], ["var(--grey)", "split unavailable"]].map(([c, l]) => h("span", {}, h("span", { class: "sw", style: "background:" + c }), l)))];
  const max = Math.max(...withY.map(i => mv(i, "ttm_yield")));
  for (const [type, list] of Object.entries(groups)) {
    const W = 560, rowH = 24, labelW = 190, H = list.length * rowH + 8;
    const svg = s("svg", { width: "100%", viewBox: `0 0 ${W + labelW + 60} ${H}`, role: "img", "aria-label": `${type} yields`, "data-testid": "bars-" + type });
    list.forEach((i, n) => {
      const y = n * rowH + 4, total = mv(i, "ttm_yield"), inc = mv(i, "income_yield"), oth = mv(i, "other_yield"), cap = mv(i, "capital_repayment_yield");
      const sc = v => (v / max) * W;
      svg.append(s("text", { x: 0, y: y + 14 }, i.name.length > 30 ? i.name.slice(0, 29) + "…" : i.name));
      if (inc !== null && oth !== null && cap !== null) {
        let x = labelW;
        for (const [v, c] of [[inc, "var(--inc)"], [oth, "var(--oth)"], [cap, "var(--cap)"]]) { svg.append(s("rect", { x, y, width: Math.max(sc(v), 0), height: 16, fill: c })); x += sc(v); }
      } else svg.append(s("rect", { x: labelW, y, width: sc(total), height: 16, fill: "var(--grey)" }));
      svg.append(s("text", { x: labelW + sc(total) + 6, y: y + 13 }, pct(total)));
    });
    out.push(h("h3", {}, type), svg);
  }
  return h("div", {}, out);
}

function lineChart(points, label) {
  if (points.length < 2) return h("p", { class: "note" }, `${label}: no history available${points.length ? " (one observation)" : ""}.`);
  const W = 560, H = 150, P = 36, xs = points.map(p => Date.parse(p[0])), ys = points.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), dy = y1 - y0 || 1;
  const X = t => P + ((t - x0) / (x1 - x0 || 1)) * (W - P - 8), Y = v => H - 22 - ((v - y0) / dy) * (H - 34);
  return h("div", {}, h("p", { class: "note" }, label), s("svg", { width: "100%", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label },
    s("polyline", { fill: "none", stroke: "var(--accent)", "stroke-width": 2, points: points.map(p => `${X(Date.parse(p[0]))},${Y(p[1])}`).join(" ") }),
    s("text", { x: 2, y: 12 }, num(y1)), s("text", { x: 2, y: H - 22 }, num(y0)),
    s("text", { x: P, y: H - 6 }, points[0][0]), s("text", { x: W - 70, y: H - 6 }, points[points.length - 1][0])));
}

function distChart(hist) {
  if (!hist.length) return h("p", { class: "note" }, "No published distribution history.");
  const W = 560, H = 160, P = 30, max = Math.max(...hist.map(d => d.total)), bw = Math.max(6, (W - P) / hist.length - 4);
  const svg = s("svg", { width: "100%", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Distribution history per payment", "data-testid": "dist-chart" });
  hist.forEach((d, n) => {
    const x = P + n * ((W - P) / hist.length), sc = v => (v / max) * (H - 40); let y = H - 22;
    const parts = d.split ? [[d.split.income, "var(--inc)"], [d.split.other, "var(--oth)"], [d.split.capital, "var(--cap)"]] : [[d.total, "var(--grey)"]];
    for (const [v, c] of parts) { y -= sc(v); svg.append(s("rect", { x, y, width: bw, height: sc(v), fill: c }, s("title", {}, `${d.ex_date}: ${v}`))); }
    if (n % Math.ceil(hist.length / 6) === 0) svg.append(s("text", { x, y: H - 6 }, d.ex_date.slice(0, 7)));
  });
  svg.append(s("text", { x: 0, y: 12 }, num(max)));
  return svg;
}

function renderDetail() {
  const i = state.data.instruments.find(x => x.key === state.selected), el = $("detail");
  if (!i) { el.hidden = true; return; }
  el.hidden = false;
  const rows = Object.entries(i.metrics).map(([n, m]) => h("tr", {}, h("td", {}, n), h("td", {}, m.value !== null && m.value !== undefined ? (m.unit === "ratio" ? pct(m.value) : num(m.value)) : (m.withheld ? "withheld" : "n/a")),
    h("td", {}, m.status), h("td", {}, (m.flags || []).join(", ")), h("td", {}, (m.reasons || m.withheld_reasons || []).join("; ")), h("td", {}, (m.sources || []).join(", "))));
  el.replaceChildren(...[
    h("h2", {}, i.name), h("p", { class: "note" }, `${i.type}${i.etf_category ? " / " + i.etf_category : ""}${i.isin ? " · ISIN " + i.isin : ""}`),
    h("h3", {}, "Distribution history (per payment)"), distChart(i.history.distributions),
    lineChart(i.history.prices, "Price history (₹)"), lineChart(i.history.navs, "NAV history (₹)"),
    i.latest.price ? h("p", { class: "note" }, `Latest price: observed ${i.latest.price.date} (${i.latest.price.venue || "venue n/a"}), retrieved ${i.latest.price.retrieved_at || "n/a"}, source ${i.latest.price.source}.`) : null,
    i.latest.nav ? h("p", { class: "note" }, `Latest NAV: as of ${i.latest.nav.date} (${i.latest.nav.grade}), retrieved ${i.latest.nav.retrieved_at || "n/a"}, source ${i.latest.nav.source}.`) : null,
    (i.open_discrepancies || []).length ? h("p", { class: "badge bad", "data-testid": "discrepancy" }, "Open source discrepancy: " + i.open_discrepancies.map(d => `${d.field} ${d.date} (${d.a} vs ${d.b})`).join("; ")) : null,
    h("h3", {}, "Metrics, status and flags"), h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["Metric", "Value", "Status", "Flags", "Reasons", "Sources"].map(x => h("th", {}, x)))), h("tbody", {}, rows)))].filter(Boolean));
}

function renderSources() {
  $("sources").replaceChildren(h("thead", {}, h("tr", {}, ...["Source", "Grade", "Access", "Display cleared", "Freshness", "Last attempt (UTC)", "Last attempt status", "Last success (UTC)", "Observed through", "Failures"].map(x => h("th", {}, x)))),
    h("tbody", {}, state.data.sources.map(x => h("tr", { "data-testid": "source-row" }, h("td", {}, x.terms_url ? h("a", { href: x.terms_url, rel: "noopener" }, x.name) : x.name), h("td", {}, x.grade), h("td", {}, x.access),
      h("td", {}, x.display_cleared ? "yes" : "no"), h("td", {}, x.freshness), h("td", {}, x.last_attempt_at || "never"), h("td", {}, x.last_attempt_status || "—"), h("td", {}, x.last_success_at || "never"), h("td", {}, x.observed_through || "—"), h("td", {}, x.consecutive_failures)))));
}

// ---- alerts: evaluated client-side on published, flag-free figures only ----
function evalAlerts() {
  const out = [], now = Date.now();
  for (const a of state.alerts) {
    const targets = a.key === "*" ? state.data.instruments : state.data.instruments.filter(i => i.key === a.key);
    for (const i of targets) {
      if (a.type === "data_stale") {
        const r = i.latest.price && i.latest.price.retrieved_at;
        if (!r || (now - Date.parse(r)) / 36e5 > a.value) out.push(`${i.name}: price data not retrieved in the last ${a.value} h`);
        continue;
      }
      const metric = { yield_above: "ttm_yield", yield_below: "ttm_yield", premium_above: "premium_to_nav", discount_below: "premium_to_nav", capital_share_above: "capital_repayment_share" }[a.type];
      const m = i.metrics[metric] || (metric === "premium_to_nav" ? i.metrics.premium_discount_to_nav : null);
      if (!m || m.value === null || !m.publishable || (m.flags || []).some(f => ["UNVERIFIED_SOURCE", "PRICE_STALE", "NAV_STALE", "SOURCE_DISCREPANCY", "AMOUNT_UNAVAILABLE_IN_WINDOW"].includes(f))) continue;
      const v = m.value * 100;
      const hit = { yield_above: v > a.value, yield_below: v < a.value, premium_above: v > a.value, discount_below: v < a.value, capital_share_above: v > a.value }[a.type];
      if (hit) out.push(`${i.name}: ${a.label} ${a.value} (now ${v.toFixed(2)}%)`);
    }
  }
  $("alerts").replaceChildren(...out.map(t => h("div", { class: "alert", "data-testid": "alert-hit" }, t)));
}
function renderAlertList() {
  $("alertlist").replaceChildren(...state.alerts.map((a, n) => h("li", { "data-testid": "alert-item" }, `${a.label} ${a.value} — ${a.key === "*" ? "all instruments" : a.key} `,
    h("button", { type: "button", onclick: () => { state.alerts.splice(n, 1); LS.set("irie.alerts", state.alerts); render(); } }, "Remove"))));
}

function csv() {
  const d = state.data, list = sorted(visible());
  const names = [...new Set(d.instruments.flatMap(i => Object.keys(i.metrics)))].sort();
  const q = v => { v = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replaceAll('"', '""') + '"' : v; };
  const head = ["key", "name", "type", "etf_category", "isin", "price", "price_date", "price_source", "price_retrieved_at",
    ...names.flatMap(n => [n, n + "_status", n + "_flags"])];
  const lines = [`# as_of ${d.as_of}; generated_at ${d.generated_at}; mode ${d.mode}`, `# ${d.notice}`, "# Blank value = unavailable or withheld, never zero. Ratios are fractions (0.05 = 5%).", head.join(",")];
  for (const i of list) {
    const p = i.latest.price || {};
    lines.push([i.key, i.name, i.type, i.etf_category, i.isin, p.value, p.date, p.source, p.retrieved_at,
      ...names.flatMap(n => { const m = i.metrics[n]; return m ? [m.value, m.status + (m.withheld ? " (withheld)" : ""), (m.flags || []).join("|")] : ["", "NOT_APPLICABLE", ""]; })].map(q).join(","));
  }
  const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv" });
  const a = h("a", { href: URL.createObjectURL(blob), download: `instruments_${d.as_of}.csv` });
  document.body.append(a); a.click(); a.remove();
}

function render() { renderCards(); renderTable(); $("yieldchart").replaceChildren(barChart(visible())); renderDetail(); renderAlertList(); evalAlerts(); }

async function init() {
  let data;
  try { data = await (await fetch("data.json", { cache: "no-cache" })).json(); }
  catch (e) { $("notice").textContent = "Could not load data.json. The dashboard needs it to render."; return; }
  state.data = data;
  $("meta").textContent = `Data as of ${data.as_of} (IST market date) · generated ${data.generated_at}`;
  $("notice").textContent = data.notice; $("notice").className = data.preview ? "preview" : "";
  const cats = [...new Set(data.instruments.map(i => i.etf_category).filter(Boolean))].sort();
  $("cat").replaceChildren(h("option", { value: "ALL" }, "All"), ...cats.map(c => h("option", { value: c }, c.replaceAll("_", " ").toLowerCase())));
  $("atype").replaceChildren(...data.alert_types.map(t => h("option", { value: t.id }, t.label)));
  $("ainst").replaceChildren(h("option", { value: "*" }, "All instruments"), ...data.instruments.map(i => h("option", { value: i.key }, i.name)));
  $("q").addEventListener("input", e => { state.q = e.target.value; render(); });
  $("type").addEventListener("change", e => { state.type = e.target.value; render(); });
  $("cat").addEventListener("change", e => { state.cat = e.target.value; render(); });
  $("onlyData").addEventListener("change", e => { state.onlyData = e.target.checked; render(); });
  $("onlyWatch").addEventListener("change", e => { state.onlyWatch = e.target.checked; render(); });
  $("csv").addEventListener("click", csv);
  $("alertform").addEventListener("submit", e => {
    e.preventDefault();
    const t = data.alert_types.find(x => x.id === $("atype").value), v = parseFloat($("aval").value);
    if (!t || !isFinite(v)) return;
    state.alerts.push({ type: t.id, label: t.label, key: $("ainst").value, value: v }); LS.set("irie.alerts", state.alerts); $("aval").value = ""; render();
  });
  renderSources(); render();
}
init();
