// The `tracebi` module an app.jsx imports. Each figure component renders the
// same data-tb-* element a template.html would hold, and the runtime
// (tracebi.js) fills it from the stamped rows — so a number shown through the
// kit is formatted, receipted and claimed exactly like one in a template. The
// build reads these components' literal props out of app.jsx to record the
// claims (tracebi/reports/app_lane.py mirrors the attribute names and ids).
import * as React from "react";
import * as ReactDOM from "react-dom";

const tb = () => window.tracebi;

let pending = false;
function scheduleRefresh() {
  if (pending) return;
  pending = true;
  const run = () => { pending = false; if (tb() && tb().refresh) tb().refresh(); };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
  else setTimeout(run, 0);
}

function useHydrate() {
  React.useLayoutEffect(() => { scheduleRefresh(); }, []);
}

const list = (v) => (Array.isArray(v) ? v.join(",") : v);
const pairs = (v) => (v && typeof v === "object" && !Array.isArray(v)
  ? Object.keys(v).map((k) => `${k}=${v[k]}`).join("; ") : v);
const flag = (v) => (v ? "" : undefined);

/** The figure id the build records for a kit figure without an `id` prop. */
export function figureId(kind, binding, key) {
  return ["fig", kind, binding, key].filter((p) => p !== undefined && p !== null && p !== "")
    .join("-").replace(/[^A-Za-z0-9_-]+/g, "-").replace(/-+$/, "");
}

/** Re-renders the component on every change of the page's selection. */
function useSelectionTick() {
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    const t = tb();
    if (!t || !t.onSelection) return undefined;
    const off = t.onSelection(() => setTick((n) => n + 1));
    setTick((n) => n + 1);     // a change between the render and this subscription
    return off;
  }, []);
  return tick;
}

/** One report.json binding's rows, live: on a live page the binding's own
 * query re-run under the current selection (the same answer the kit's
 * figures show), re-rendering when the selection changes; with "embed":
 * "none", or a binding the page engine cannot run (SQL, report.py), the
 * stamped rows. Copies, never re-queried. `keep` ("dim.col" or a list)
 * names fields whose other values stay, for a chart that dims them. What
 * you draw from them is live, not receipted. */
export function useBinding(name, keep) {
  const tick = useSelectionTick();
  const k = list(keep) || "";
  return React.useMemo(() => {
    const t = tb();
    if (!t) return [];
    return t.rows ? t.rows(name, k ? k.split(",") : undefined) : t.data(name);
  }, [name, k, tick]);
}

/** The page's current selection ({"dim_region.region": ["East"], …}; {} when
 * nothing is picked or the page is not live), re-rendering when it changes. */
export function useSelection() {
  const tick = useSelectionTick();
  return React.useMemo(() => (tb() && tb().selection ? tb().selection() : {}), [tick]);
}

/** TraceBi's number formatting ("compact", "currency0", "percent", …). */
export function fmt(value, mode) {
  return tb() ? tb().format(value, mode) : String(value);
}

export function Value({ binding, cell, format, id, className, ...rest }) {
  useHydrate();
  return (
    <span {...rest} className={className} id={id || figureId("value", binding, cell)}
      data-tb-figure="value" data-tb-binding={binding} data-tb-cell={cell}
      data-tb-format={format} />
  );
}

/** A KPI card. `deltaBinding` / `deltaCell` name a stamped change (a measure
 * the model computes, e.g. fair value less cost), shown first on the context
 * line with its arrow, sign and colour; `deltaGood="up|down"` says which way
 * is good. No comparison measure, no delta: the kit never computes one. A
 * <Spark> child sits on the card's bottom edge. */
export function Kpi({ binding, cell, format, label, context, lead, id, className, children,
                      deltaBinding, deltaCell, deltaFormat, deltaGood, ...rest }) {
  useHydrate();
  const cls = ["tb-kpi", lead ? "tb-kpi--lead" : "", className || ""].filter(Boolean).join(" ");
  const delta = deltaBinding != null && (
    <span className="tb-kpi-delta" id={figureId("delta", deltaBinding, deltaCell)}
      data-tb-figure="value" data-tb-binding={deltaBinding} data-tb-cell={deltaCell}
      data-tb-format={deltaFormat}
      data-tb-direction={deltaGood ? `${deltaGood}-good` : undefined} />
  );
  return (
    <div {...rest} className={cls} id={id || figureId("value", binding, cell)}
      data-tb-figure="value" data-tb-binding={binding} data-tb-cell={cell}
      data-tb-format={format}>
      {label != null && <span className="tb-kpi-label">{label}</span>}
      <span className="tb-kpi-value" />
      {(context != null || delta) && (
        <span className="tb-kpi-context">{delta}{delta && context != null ? " " : null}{context}</span>
      )}
      {children}
    </div>
  );
}

// ── The chart: <EChart>, and <Chart> / <Spark> as its presets ─────────────
//
// Every chart is drawn by Apache ECharts, through the runtime's one chart
// engine (tracebi.js "The chart engine"): the option builder and the ECharts
// theme a template's {{ figure() }} chart is drawn with. Its receipt follows
// the data, not the author: given a literal binding, x and y, an <EChart>
// plots that binding's columns as they are; it renders the same
// data-tb-figure="chart" element a template holds, the build records it as a
// claim (and refuses an unknown binding or column), and the runtime draws
// it, live under the page's selection, a click on a mark writing the
// selection. <Chart> and <Spark> are that chart with the kit's defaults (a
// bar; a bare area under a KPI). Given only an option, a chart's numbers were
// computed in the page: it carries data-tb-computed, is not a claim, and
// draws itself here, in the same theme.

const KIT_TYPES = { bar: 1, barh: 1, line: 1, area: 1, pie: 1, scatter: 1 };
const NAMED_TYPES = { pie: 1, funnel: 1, treemap: 1, sunburst: 1 };

/** The kit chart type the build's no-JavaScript picture draws for an ECharts
 * series type (app_lane.py mirrors it). */
export function kitChartType(type) {
  const t = type || "bar";
  return KIT_TYPES[t] ? t : NAMED_TYPES[t] ? "pie" : "bar";
}

const engine = () => (tb() && tb()._echarts) || null;

/** The house chart tokens (tracebi.css, docs/reference/chart-style.md), read
 * from the page now: what every chart is drawn with. */
export function chartTokens() {
  return engine() ? engine().tokens() : {};
}

/** The TraceBi theme for ECharts, from the chart tokens: the house look
 * (chart-style.md) as ECharts' defaults. */
export function echartsTheme() {
  return engine() ? engine().theme() : {};
}

/** Calls fn when the page's ground changes: its data-tb-mode, or the reader's
 * system preference that data-tb-mode="auto" follows. */
function onModeChange(fn) {
  const root = document.documentElement;
  const mo = new MutationObserver(fn);
  mo.observe(root, { attributes: true, attributeFilter: ["data-tb-mode", "class", "style"] });
  const mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (mq) mq.addEventListener ? mq.addEventListener("change", fn) : mq.addListener(fn);
  return () => {
    mo.disconnect();
    if (mq) mq.removeEventListener ? mq.removeEventListener("change", fn) : mq.removeListener(fn);
  };
}

function picked(selection, field) {
  const v = field && selection ? selection[field] : null;
  if (!Array.isArray(v) || !v.length) return null;
  const out = {};
  v.forEach((x) => { out[x === true ? "True" : x === false ? "False" : String(x)] = true; });
  return out;
}

/** The chart. With `binding`, `x` and `y` (literal strings: they are its
 * claim) it plots that binding's columns as they are: `type` bar, barh,
 * line, area, pie, scatter or any ECharts series type that takes name/value
 * items (funnel, treemap, sunburst, …), `series` a column that splits the
 * rows into series, `format` / `unit` for its values, `stack`, and the
 * kit's `mark`, `annotate`, `facet`, `xTitle`, `yTitle`, `palette`.
 * `option` (an ECharts option, or a function of the rows) deep-merges on
 * top: the escape hatch for anything the props do not say, which styles the
 * binding's numbers and never replaces them. With `option` alone (and
 * `binding` to draw from, or none) the chart's numbers are the page's own:
 * not a claim. Every chart is live: its rows are its binding's query re-run
 * under the page's selection, and a click on a mark writes the selection for
 * its `x` (`selects="dim.col"` on an option-only chart; `onSelect(params)`
 * returns the value a click picks, or null for none; shift adds). Its own
 * field's other values stay and are dimmed; `highlight="off"` (or
 * data-tb-highlight="off" on an ancestor) narrows instead. It draws in the
 * house look (docs/reference/chart-style.md) from the page's chart tokens,
 * so a theme or the project's brand restyles it. `renderer` "svg" (the
 * default: vectors, tabular figures, the print) or "canvas" (thousands of
 * marks); `theme` "auto" follows the page's tokens and mode, or an ECharts
 * theme object or name; `onEvents` maps an ECharts event name to a handler.
 * `ariaLabel` describes the chart. */
export function EChart(props) {
  const ys = (list(props.y) || "").split(",").map((s) => s.trim()).filter(Boolean);
  const claimed = typeof props.binding === "string" && props.binding !== "" &&
    typeof props.x === "string" && props.x !== "" && ys.length > 0;
  return claimed || props.preset ? <ClaimedChart {...props} ys={ys} /> : <ComputedChart {...props} />;
}

/** A bar chart (or any `type`) of a binding's columns: <EChart> with
 * `color` naming the series column. */
export function Chart({ color, series, height, style, ...rest }) {
  const st = height ? { height, ...(style || {}) } : style;
  return <EChart {...rest} series={series || color} style={st} preset="chart" />;
}

/** A line or area chart drawn as a sparkline: the trend's shape under a KPI. */
export function Spark({ color, series, ...rest }) {
  return <EChart {...rest} series={series || color} preset="spark" />;
}

function ClaimedChart({ binding, x, ys, series, type, format, valueFormat, unit, stack, mark,
                        annotate, facet, xTitle, yTitle, palette, onSelect, option, highlight,
                        id, renderer, height, theme, className, onEvents, ariaLabel, style,
                        preset }) {
  useHydrate();
  const ref = React.useRef(null);
  const last = React.useRef(null);
  // The runtime's engine reads these at every draw; a change of one redraws.
  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const opts = { option, onEvents, onSelect, ariaLabel, height, theme, renderer };
    el.__tbChart = opts;
    const prev = last.current;
    last.current = opts;
    if (prev && el.__tbRedraw && Object.keys(opts).some((k) => opts[k] !== prev[k])) el.__tbRedraw();
  });
  const spark = preset === "spark";
  const t = type || (spark ? "area" : "bar");
  const kit = kitChartType(t);
  const cls = [spark ? "tb-spark" : "", className || ""].join(" ").trim();
  return (
    <div ref={ref} className={cls || undefined} style={style}
      id={id || figureId(spark ? "spark" : "chart", binding, ys.join(","))}
      data-tb-figure="chart" data-tb-binding={binding} data-tb-type={kit}
      data-tb-echart-type={kit === t ? undefined : t}
      data-tb-x={x} data-tb-y={ys.join(",")} data-tb-color={series}
      data-tb-value-format={format || valueFormat} data-tb-unit={unit}
      data-tb-stack={flag(stack)} data-tb-mark={list(mark)} data-tb-annotate={pairs(annotate)}
      data-tb-facet={facet} data-tb-x-title={xTitle} data-tb-y-title={yTitle}
      data-tb-palette={list(palette)} data-tb-renderer={renderer}
      data-tb-highlight={highlight} />
  );
}

/** An option-only chart: the page's own numbers, drawn in the house theme,
 * live, and a click writes `selects`. Not a claim. */
function ComputedChart({ binding, selects, onSelect, option, highlight, id, renderer = "svg",
                         height = 320, theme = "auto", className, onEvents, ariaLabel, style }) {
  useHydrate();
  const outer = React.useRef(null);
  const host = React.useRef(null);
  const chart = React.useRef(null);

  const [off, setOff] = React.useState(highlight === "off");
  React.useLayoutEffect(() => {
    const el = outer.current;
    setOff(highlight === "off" || !!(el && el.closest && el.closest('[data-tb-highlight="off"]')));
  }, [highlight]);
  const [modeTick, setModeTick] = React.useState(0);
  React.useEffect(() => (theme === "auto" ? onModeChange(() => setModeTick((n) => n + 1)) : undefined), [theme]);

  const rows = useBinding(binding, off || !selects ? [] : [selects]);
  const selection = useSelection();
  const resolved = React.useMemo(() => {
    const over = typeof option === "function" ? option(rows) : option;
    const e = engine();
    const set = off ? null : picked(selection, selects);
    return e && set ? e.dim(over || {}, set) : (over || {});
  }, [rows, selection, option, off, selects, modeTick]);

  const latest = React.useRef(resolved);
  latest.current = resolved;
  const handlers = React.useRef(onEvents);
  handlers.current = onEvents;
  const select = React.useRef(null);
  select.current = selects ? (params) => {
    const value = onSelect ? onSelect(params) : params && params.name;
    if (value === null || value === undefined || value === "") return;
    const ev = params && params.event && params.event.event;
    if (tb() && tb().pick) tb().pick(selects, String(value), ev);
  } : null;

  const full = (opt) => {
    const o = opt || {};
    if (o.aria !== undefined) return o;
    return { ...o, aria: { enabled: true, decal: { show: false },
      ...(ariaLabel ? { label: { description: ariaLabel } } : {}) } };
  };

  const [ready, setReady] = React.useState(0);
  React.useEffect(() => {
    const echarts = window.__tbModules && window.__tbModules.echarts;
    if (!echarts) throw new Error("<EChart> needs ECharts, which this page did not load.");
    const auto = theme === "auto";
    let applied = auto ? echartsTheme() : theme;
    const c = echarts.init(host.current, applied, { renderer });
    chart.current = c;
    c.setOption(full(latest.current), { notMerge: true });
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => c.resize()) : null;
    if (ro) ro.observe(host.current);
    // Laid out on paper (and back), drawn at that width at once: the observer
    // would only report it after the page has printed. flush paints now; a
    // resize alone paints on the next frame, after the print.
    const paper = window.matchMedia ? window.matchMedia("print") : null;
    const reprint = () => { c.resize(); if (c.getZr) c.getZr().flush(); };
    if (paper) paper.addEventListener ? paper.addEventListener("change", reprint) : paper.addListener(reprint);
    const offMode = auto ? onModeChange(() => {
      const next = echartsTheme();
      if (JSON.stringify(next) === JSON.stringify(applied)) return;
      applied = next;
      c.setTheme(next);
    }) : () => {};
    c.on("click", (p) => { if (select.current) select.current(p); });
    setReady((n) => n + 1);
    return () => {
      offMode();
      if (ro) ro.disconnect();
      if (paper) paper.removeEventListener ? paper.removeEventListener("change", reprint) : paper.removeListener(reprint);
      c.dispose();
      chart.current = null;
    };
  }, [renderer, typeof theme === "string" ? theme : JSON.stringify(theme)]);

  React.useEffect(() => {
    if (chart.current) chart.current.setOption(full(resolved), { notMerge: true });
  }, [resolved, ariaLabel]);

  const names = onEvents ? Object.keys(onEvents).sort().join(",") : "";
  React.useEffect(() => {
    const c = chart.current;
    if (!c || !names) return undefined;
    const bound = names.split(",").map((name) => {
      const h = (p) => { const f = handlers.current && handlers.current[name]; if (f) f(p, c); };
      c.on(name, h);
      return [name, h];
    });
    return () => { if (!c.isDisposed()) bound.forEach(([name, h]) => c.off(name, h)); };
  }, [ready, names]);

  return (
    <div ref={outer} className={["tb-echart", className || ""].join(" ").trim()} style={style}
      data-tb-highlight={highlight} id={id} data-tb-computed="">
      <div ref={host} role="img" aria-label={ariaLabel} style={{ height, width: "100%" }} />
    </div>
  );
}

/** A table. `selectRows`: on a live page a click on a row selects its values
 * of the dimension columns the table shows (again, it clears them), and every
 * figure re-runs under the selection; `selectRows="dim_issuer.issuer"` (or a
 * list) names the columns a row click writes. */
export function Table({ binding, columns, labels, formats, sort, bars, totals, rows, id, className,
                        selectRows }) {
  useHydrate();
  const n = rows === "all" ? null : Number(rows || 10);
  // The scroll box is rendered here, not wrapped in by the runtime: React owns
  // this element's parent and must never find it moved.
  return (
    <div className="tb-scroll" style={n ? { maxHeight: `${(n + 1) * 2.6}em` } : undefined}>
      <table className={className} id={id || figureId("table", binding)}
        data-tb-figure="table" data-tb-binding={binding}
        data-tb-columns={list(columns)} data-tb-labels={pairs(labels)}
        data-tb-formats={pairs(formats)} data-tb-sort={flag(sort)}
        data-tb-bars={list(bars)} data-tb-totals={totals}
        data-tb-rows={rows === undefined ? undefined : String(rows)}
        data-tb-select-rows={selectRows === true ? "" : selectRows ? list(selectRows) : undefined} />
    </div>
  );
}

/** A filter on the page's selection. On a live page (a slice, the default)
 * every filter cuts the whole page: each figure it reaches reruns its own
 * query, KPIs included; `multiple` picks several values. On a page built with
 * embed none it subsets one binding's rows (or, with no binding, every
 * binding that has the column) and KPIs stay the stamped totals. */
export function Filter({ binding, column, label, className, multiple }) {
  useHydrate();
  const select = <select data-tb-filter="" data-tb-binding={binding || "*"} data-tb-column={column}
    multiple={multiple || undefined} />;
  return label ? <label className={className}>{label} {select}</label> : select;
}

/** A range on the page's selection: two handles over a number column (a
 * holding's fair value), or from/to pickers over a time grain's labels
 * (dim_date.month). It writes {gte, lte} and lets go at the full domain.
 * `min` / `max` bound the track; `step` its increments. */
export function Range({ column, label, min, max, step, className }) {
  useHydrate();
  return <div className={className} data-tb-range="" data-tb-column={column}
    data-tb-label={label} data-tb-min={min} data-tb-max={max} data-tb-step={step} />;
}

/** Where the selection bar goes: one chip per picked value, Clear, and
 * "Download what I see". Without one, the runtime puts the bar above the
 * app. Hidden while the page is as built. */
export function SelectionBar({ className }) {
  useHydrate();
  return <div className={className} data-tb-selection="" />;
}

export function Search({ binding, placeholder, label, className }) {
  useHydrate();
  const input = <input data-tb-search="" data-tb-binding={binding}
    placeholder={placeholder || "Search…"} />;
  return label ? <label className={className}>{label} {input}</label> : input;
}

export function Download({ binding, label }) {
  useHydrate();
  return <button type="button" data-tb-download="" data-tb-binding={binding}
    data-tb-label={label || "Download CSV"} />;
}

/** When this file was built, from its receipt ("Built Oct 16, 2026, 6:10 PM").
 * A fact about the build, never typed in. */
export function Built({ className }) {
  useHydrate();
  return <span className={className} data-tb-built="" />;
}

/** The model's label, which the build writes on the app's mount point: the
 * kicker a masthead shows when its author gave none. */
function modelKicker() {
  const host = typeof document === "undefined" ? null : document.getElementById("tb-app");
  return host ? host.getAttribute("data-tb-kicker") : null;
}

/** The project's firm mark (tracebi.yaml brand: name and logo), which the
 * build writes on the app's mount point: the logo, then the name beside it.
 * null when the project sets neither. Never the kicker. */
function brandMark() {
  const host = typeof document === "undefined" ? null : document.getElementById("tb-app");
  if (!host || !host.hasAttribute("data-tb-brand")) return null;
  const name = host.getAttribute("data-tb-brand");
  return (
    <span className="tb-brand">
      {host.hasAttribute("data-tb-brand-logo") && <span className="tb-brand-logo" aria-hidden="true" />}
      {name && <span className="tb-brand-name">{name}</span>}
    </span>
  );
}

/** The masthead that opens the page: an optional mark, a kicker, the title
 * (a string, or text with <Value> figures in it), the standfirst (children),
 * and a meta line with the period the numbers cover, when the file was built
 * and the verdict chip, both filled by the runtime from the file itself.
 * The kicker defaults to the model's label; an explicit one wins, and
 * kicker={null} shows none. The mark defaults to the project's brand (its
 * logo and name); an explicit one wins, and mark={null} shows none.
 * `period` is presentation ("Q3 2026"); the title's own numbers are figures.
 * Other props (data-tb-title="center|banner|nav") go on the <header>. */
export function Masthead({ title, kicker, period, mark, className, children, ...rest }) {
  useHydrate();
  const shown = kicker === undefined ? modelKicker() : kicker;
  return (
    <header {...rest} className={["tb-masthead", className || ""].join(" ").trim()}>
      <div className="tb-masthead-mark">{mark === undefined ? brandMark() : mark}</div>
      {shown != null && shown !== "" && <p className="tb-kicker">{shown}</p>}
      <h1>{title}</h1>
      {children != null && <div className="tb-standfirst">{children}</div>}
      <div className="tb-masthead-meta">
        {period != null && <span className="tb-masthead-period">{period}</span>}
        <span data-tb-built="" />
        <span className="tb-verdict" />
      </div>
    </header>
  );
}

/** Where the page's footer goes: the build writes it (the one line on how
 * these numbers were made, and its disclosure) after the app; <Footer />
 * moves it here, so it ends this column (a sidebar layout's main). */
export function Footer({ className }) {
  const ref = React.useRef(null);
  React.useLayoutEffect(() => {
    const foot = document.getElementById("tb-footer");
    const slot = ref.current;
    if (!foot || !slot) return undefined;
    const home = foot.parentNode;
    slot.appendChild(foot);
    return () => { if (home) home.appendChild(foot); };
  }, []);
  return <div ref={ref} className={className} data-tb-footer-slot="" />;
}


// ── App state that a shared link carries ────────────────────────────────────

function readHash() {
  const out = {};
  const h = (window.location.hash || "").replace(/^#/, "");
  h.split("&").forEach((part) => {
    if (!part) return;
    const i = part.indexOf("=");
    const k = decodeURIComponent(i < 0 ? part : part.slice(0, i));
    out[k] = i < 0 ? "" : decodeURIComponent(part.slice(i + 1));
  });
  return out;
}

function writeHash(state) {
  const h = Object.keys(state).filter((k) => state[k] !== undefined && state[k] !== "")
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(state[k])}`).join("&");
  try { window.history.replaceState(null, "", h ? `#${h}` : window.location.pathname + window.location.search); }
  catch (e) { window.location.hash = h; }
}

// ── Printing ───────────────────────────────────────────────────────────────

// One flag for the page: true from the browser's beforeprint to its afterprint
// (Ctrl+P, and `tracebi report build --format pdf`, which dispatches it).
let printing = false;
const printSubs = new Set();
function setPrinting(v) {
  if (printing === v) return;
  printing = v;
  // Synchronously, so the print layout already holds every view — and their
  // figures filled, before the next frame would have done it.
  ReactDOM.flushSync(() => printSubs.forEach((f) => f(v)));
  if (v && tb() && tb().refresh) tb().refresh();
}
if (typeof window !== "undefined") {
  window.addEventListener("beforeprint", () => setPrinting(true));
  window.addEventListener("afterprint", () => setPrinting(false));
}

/** True while the page is being printed. An app with views renders all of
 * them then, so a PDF or a paper copy holds the whole report, not the view
 * that happened to be open. */
export function usePrinting() {
  const [v, set] = React.useState(printing);
  React.useEffect(() => {
    printSubs.add(set);
    set(printing);
    return () => { printSubs.delete(set); };
  }, []);
  return v;
}

/** useState kept in the page's URL (#view=Detail&period=YTD), so a shared
 * link — or a reload — opens where the reader was. Values are strings. */
export function useUrlState(key, initial) {
  const [value, setValue] = React.useState(() => {
    const v = readHash()[key];
    return v === undefined ? initial : v;
  });
  const set = React.useCallback((next) => {
    setValue((prev) => {
      const v = typeof next === "function" ? next(prev) : next;
      const state = readHash();
      if (v === initial) delete state[key]; else state[key] = String(v);
      writeHash(state);
      return v;
    });
  }, [key, initial]);
  return [value, set];
}

/** A segmented control: one choice of a few ("MTD", "QTD", "YTD"). Use it to
 * pick WHICH figure shows — each option its own binding, so each number keeps
 * its receipt — never to compute one. */
export function Segmented({ options, value, onChange, label, className }) {
  return (
    <div role="radiogroup" aria-label={label}
      className={["tb-segmented", className || ""].join(" ").trim()}>
      {options.map((opt) => {
        const v = typeof opt === "string" ? opt : opt.value;
        const text = typeof opt === "string" ? opt : opt.label;
        return (
          <button key={v} type="button" role="radio" aria-checked={value === v}
            className={value === v ? "tb-segmented-on" : ""} onClick={() => onChange(v)}>
            {text}
          </button>
        );
      })}
    </div>
  );
}
