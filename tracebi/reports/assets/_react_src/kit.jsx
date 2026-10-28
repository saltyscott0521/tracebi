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
  return tb() ? tb().fmt(value, mode) : String(value);
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

function chartProps(kind, p) {
  return {
    id: p.id || figureId(kind, p.binding, list(p.y)),
    "data-tb-figure": "chart",
    "data-tb-binding": p.binding,
    "data-tb-type": p.type || (kind === "spark" ? "area" : "bar"),
    "data-tb-x": p.x,
    "data-tb-y": list(p.y),
    "data-tb-color": p.color,
    "data-tb-value-format": p.valueFormat,
    "data-tb-stack": flag(p.stack),
    "data-tb-mark": list(p.mark),
    "data-tb-annotate": pairs(p.annotate),
    "data-tb-facet": p.facet,
    "data-tb-unit": p.unit,
    "data-tb-x-title": p.xTitle,
    "data-tb-y-title": p.yTitle,
    "data-tb-palette": list(p.palette),
  };
}

export function Chart(props) {
  useHydrate();
  const style = props.height ? { height: props.height, ...(props.style || {}) } : props.style;
  return <div className={props.className} style={style} {...chartProps("chart", props)} />;
}

/** A line or area chart drawn as a sparkline: the trend's shape under a KPI. */
export function Spark(props) {
  useHydrate();
  return <div className={["tb-spark", props.className || ""].join(" ").trim()}
    style={props.style} {...chartProps("spark", props)} />;
}

// ── <EChart>: the chart, drawn by Apache ECharts ────────────────────────────
//
// One chart component for every chart of an app. Its receipt follows the
// data, not the author: given a literal binding, x and y it plots that
// binding's columns as they are, renders the same data-tb-figure="chart"
// element the kit's <Chart> does, and the build records it as a claim (and
// refuses an unknown binding or column). Given only an option, its numbers
// were computed in the page: it carries data-tb-computed and is not a claim.
// Either way it filters live (its rows are the binding's query re-run under
// the page's selection) and a click on a mark writes the selection.
// ECharts draws into its own div (canvas or SVG), so the React runtime never
// reconciles its marks.

let colorCtx = null;
/** A token as a colour ECharts can parse (a theme may write oklch() or
 * color-mix()); the canvas normalises it, as the browser resolved it. */
function plainColor(v) {
  if (!v) return v;
  try {
    colorCtx = colorCtx || document.createElement("canvas").getContext("2d");
    colorCtx.fillStyle = "#000";
    colorCtx.fillStyle = v;
    return colorCtx.fillStyle;
  } catch (e) { return v; }
}

/** The TraceBi theme for ECharts, read from the page's tokens now: the same
 * ink, muted, rule and card colours, and the same series palette
 * (--tb-chart-1…8), that the D3 engine draws the kit's <Chart> with. */
export function echartsTheme() {
  const cs = getComputedStyle(document.documentElement);
  const tok = (n) => { const v = cs.getPropertyValue(`--tb-${n}`).trim(); return v ? plainColor(v) : undefined; };
  const ink = tok("ink"), muted = tok("muted"), rule = tok("rule"), card = tok("bg");
  const font = cs.getPropertyValue("--tb-font").trim() || undefined;
  const palette = [];
  for (let i = 1; i <= 8; i++) { const c = tok(`chart-${i}`); if (c) palette.push(c); }
  const axis = {
    axisLine: { lineStyle: { color: rule } },
    axisTick: { lineStyle: { color: rule } },
    axisLabel: { color: muted },
    splitLine: { lineStyle: { color: rule } },
    splitArea: { areaStyle: { color: ["transparent"] } },
    nameTextStyle: { color: muted },
  };
  return {
    color: palette.length ? palette : undefined,
    backgroundColor: "transparent",
    textStyle: { color: ink, fontFamily: font },
    title: { textStyle: { color: ink }, subtextStyle: { color: muted } },
    legend: { textStyle: { color: ink }, pageTextStyle: { color: muted },
              pageIconColor: ink, pageIconInactiveColor: rule },
    tooltip: { backgroundColor: card, borderColor: rule, textStyle: { color: ink } },
    categoryAxis: axis, valueAxis: axis, logAxis: axis, timeAxis: axis,
    radar: { axisName: { color: muted }, axisLine: { lineStyle: { color: rule } },
             splitLine: { lineStyle: { color: rule } }, splitArea: { show: false } },
    visualMap: { textStyle: { color: muted } },
    dataZoom: { textStyle: { color: muted }, borderColor: rule },
    toolbox: { iconStyle: { borderColor: muted } },
    markLine: { label: { color: muted } },
    label: { color: ink },
  };
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

const KIT_TYPES = { bar: 1, barh: 1, line: 1, area: 1, pie: 1, scatter: 1 };
const NAMED_TYPES = { pie: 1, funnel: 1, treemap: 1, sunburst: 1 };
const AXIS_TYPES = { bar: 1, barh: 1, line: 1, area: 1, effectScatter: 1, pictorialBar: 1 };

/** The kit chart type the build's no-JavaScript picture draws for an ECharts
 * series type (app_lane.py mirrors it). */
export function kitChartType(type) {
  const t = type || "bar";
  return KIT_TYPES[t] ? t : NAMED_TYPES[t] ? "pie" : "bar";
}

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const toNum = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

/** `over` deep-merged onto `base`: objects key by key, arrays of objects item
 * by item (series[0] onto series[0]), anything else replaced. */
function mergeOption(base, over) {
  if (over === undefined) return base;
  if (Array.isArray(over)) {
    if (!Array.isArray(base) || !over.some(isObj)) return over;
    const n = Math.max(base.length, over.length);
    return Array.from({ length: n }, (_, i) => (i < over.length ? mergeOption(base[i], over[i]) : base[i]));
  }
  if (!isObj(over)) return over;
  const out = isObj(base) ? { ...base } : {};
  for (const k of Object.keys(over)) out[k] = mergeOption(out[k], over[k]);
  return out;
}

/** An override with its data taken out: on a receipted chart the numbers
 * are the binding's, so the escape hatch styles them and cannot replace
 * them (series data, a dataset, category labels). */
function withoutData(over) {
  if (!isObj(over)) return over;
  const o = { ...over };
  delete o.dataset;
  const strip = (v, key) => (Array.isArray(v) ? v.map((x) => strip(x, key))
    : isObj(v) ? (() => { const c = { ...v }; delete c[key]; return c; })() : v);
  if (o.series !== undefined) o.series = strip(o.series, "data");
  if (o.xAxis !== undefined) o.xAxis = strip(o.xAxis, "data");
  if (o.yAxis !== undefined) o.yAxis = strip(o.yAxis, "data");
  return o;
}

function picked(selection, field) {
  const v = field && selection ? selection[field] : null;
  if (!Array.isArray(v) || !v.length) return null;
  return new Set(v.map((x) => (x === true ? "True" : x === false ? "False" : String(x))));
}

/** A colour at a quarter strength: #rrggbb or rgb() → rgba(). */
function faded(c) {
  const hex = /^#([0-9a-f]{6})$/i.exec(c);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},0.25)`;
  }
  const rgb = /^rgba?\(([^,]+),([^,]+),([^,)]+)/.exec(c);
  return rgb ? `rgba(${rgb[1]},${rgb[2]},${rgb[3]},0.25)` : c;
}

/** The values a chart's own field did not pick recede, as the kit's chart
 * dims them; a pick none of its marks carries dims nothing. */
function dimOption(opt, set) {
  if (!set || !isObj(opt) || !opt.series) return opt;
  const axisCats = (a) => {
    const ax = Array.isArray(a) ? a[0] : a;
    return ax && Array.isArray(ax.data) ? ax.data.map((d) => String(isObj(d) ? d.value : d)) : null;
  };
  const cats = axisCats(opt.xAxis) || axisCats(opt.yAxis);
  let hit = false;
  const walk = (data, byIndex) => data.map((d, i) => {
    let item = d;
    if (isObj(d) && Array.isArray(d.children)) item = { ...d, children: walk(d.children, false) };
    const name = isObj(d) && d.name != null ? String(d.name) : byIndex && cats ? cats[i] : null;
    if (name == null) return item;
    if (set.has(name)) { hit = true; return item; }
    const o = isObj(item) ? { ...item } : { value: item };
    o.itemStyle = { ...(o.itemStyle || {}), opacity: 0.25 };
    // A treemap or sunburst cell ignores opacity: its own colour fades.
    if (typeof o.itemStyle.color === "string") o.itemStyle.color = faded(o.itemStyle.color);
    return o;
  });
  const list = Array.isArray(opt.series) ? opt.series : [opt.series];
  const series = list.map((s) => (isObj(s) && Array.isArray(s.data) ? { ...s, data: walk(s.data, true) } : s));
  return hit ? { ...opt, series } : opt;
}

function formatter(format, unit) {
  return (v) => {
    const t = tb();
    const out = t && t.format ? t.format(v, format) : String(v);
    return out === "" ? out : out + (unit || "");
  };
}

/** Axis ticks are short: compact digits, keeping a currency sign or a
 * percent, as the kit's chart writes them. */
function tickFormatter(format, unit) {
  return (v) => {
    const t = tb(), n = Number(v);
    if (!t || !t.format) return String(v);
    const out = format === "percent" ? t.format(n, "percent")
      : /^currency/.test(format || "") ? (n < 0 ? "-$" : "$") + t.format(Math.abs(n), "compact")
      : t.format(n, "compact");
    return out + (unit || "");
  };
}

function firstSeen(rows, col) {
  const seen = new Set(), out = [];
  for (const r of rows) { const v = r[col]; if (!seen.has(v)) { seen.add(v); out.push(v); } }
  return out;
}

/** The option for a binding's columns: x the category (a number on a
 * scatter), y one measure or several, `series` a column whose values split
 * the rows into series. Colours come from the binding's stamped rows, so a
 * category or a series keeps its colour whatever the selection leaves. */
function optionFromRows({ type, rows, stamped, x, ys, series, format, unit, stack, palette, xSet, sSet }) {
  const t = type || "bar";
  const value = formatter(format, unit);
  const tick = tickFormatter(format, unit);
  const color = (keys, k) => (palette && palette.length ? palette[Math.max(0, keys.indexOf(k)) % palette.length] : undefined);
  if (t === "scatter") {
    return {
      tooltip: { trigger: "item", valueFormatter: value },
      xAxis: { type: "value", axisLabel: { formatter: tick } },
      yAxis: { type: "value", axisLabel: { formatter: tick }, name: unit || undefined },
      series: ys.map((y) => ({ type: "scatter", name: y,
        data: rows.map((r) => [toNum(r[x]), toNum(r[y])]) })),
    };
  }
  if (!AXIS_TYPES[t]) {
    // A share of a whole (pie, funnel, treemap, sunburst, …): one item per row.
    const keys = firstSeen(stamped, x);
    const item = (r) => ({ name: r[x], value: toNum(r[ys[0]]),
      itemStyle: { color: color(keys, r[x]) } });
    const s = { type: t, name: ys[0], data: rows.map(item) };
    if (t === "pie") Object.assign(s, { radius: ["42%", "70%"], avoidLabelOverlap: true });
    if (t === "treemap") Object.assign(s, { nodeClick: false, roam: false, breadcrumb: { show: false } });
    if (t === "sunburst") s.nodeClick = false;
    return dimOption({ tooltip: { trigger: "item", valueFormatter: value }, series: [s] }, xSet);
  }
  const horizontal = t === "barh";
  const kind = t === "barh" ? "bar" : t === "area" ? "line" : t;
  const cats = firstSeen(rows, x);
  const index = new Map(cats.map((c, i) => [c, i]));
  let out;
  if (series) {
    const keys = firstSeen(stamped, series);
    const present = new Set(rows.map((r) => r[series]));
    const y = ys[0];
    out = keys.filter((k) => present.has(k)).map((k) => {
      const data = cats.map(() => null);
      for (const r of rows) if (r[series] === k) data[index.get(r[x])] = toNum(r[y]);
      const dim = sSet && !sSet.has(String(k));
      return { type: kind, name: String(k), data, itemStyle: { color: color(keys, k), opacity: dim ? 0.25 : undefined },
               lineStyle: dim ? { opacity: 0.25 } : undefined };
    });
  } else {
    out = ys.map((y) => {
      const data = cats.map(() => null);
      for (const r of rows) data[index.get(r[x])] = toNum(r[y]);
      return { type: kind, name: y, data, itemStyle: { color: color(ys, y) } };
    });
  }
  out.forEach((s) => {
    if (t === "area") s.areaStyle = { opacity: 0.25 };
    if (kind === "line") { s.showSymbol = cats.length <= 40; s.smooth = false; }
    if (kind === "bar") { s.barMaxWidth = 48; s.itemStyle.borderRadius = horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]; }
    if (stack) s.stack = "total";
  });
  const catAxis = { type: "category", data: cats, inverse: horizontal };
  const valAxis = { type: "value", axisLabel: { formatter: tick }, name: unit || undefined };
  return dimOption({
    tooltip: { trigger: "axis", axisPointer: { type: kind === "bar" ? "shadow" : "line" }, valueFormatter: value },
    legend: out.length > 1 ? { type: "scroll", top: 0 } : undefined,
    grid: { left: 8, right: 16, top: out.length > 1 ? 36 : 16, bottom: 8 },
    xAxis: horizontal ? valAxis : catAxis,
    yAxis: horizontal ? catAxis : valAxis,
    series: out,
  }, xSet);
}

/** The chart. With `binding`, `x` and `y` (literal strings: they are its
 * claim) it plots that binding's columns as they are: `type` bar, barh,
 * line, area, pie, scatter or any ECharts series type that takes name/value
 * items (funnel, treemap, sunburst, …), `series` a column that splits the
 * rows into series, `format` / `unit` for its values, `stack`. `option` (an
 * ECharts option, or a function of the rows) deep-merges on top: the escape
 * hatch for anything the props do not say, which styles the binding's
 * numbers and never replaces them. With `option` alone (and `binding` to
 * draw from, or none) the chart's numbers are the page's own: not a claim.
 * Every chart is live: its rows are its binding's query re-run under the
 * page's selection, and a click on a mark writes the selection for its `x`
 * (`selects="dim.col"` on an option-only chart; `onSelect(params)` returns
 * the value a click picks, or null for none; shift adds). Its own field's
 * other values stay and are dimmed, as on the kit's charts;
 * `highlight="off"` (or data-tb-highlight="off" on an ancestor) narrows
 * instead. `renderer` "canvas" (the default: large data) or "svg"; `theme`
 * "auto" follows the page's tokens and mode, or an ECharts theme object or
 * name; `onEvents` maps an ECharts event name to a handler. ECharts' aria is
 * on unless the option sets its own; `ariaLabel` describes the chart. */
export function EChart({ binding, x, y, series, type, format, valueFormat, unit, stack,
                         selects, onSelect, option, highlight, id,
                         renderer = "canvas", height = 320, theme = "auto",
                         className, onEvents, ariaLabel, style }) {
  useHydrate();
  const outer = React.useRef(null);
  const host = React.useRef(null);
  const chart = React.useRef(null);
  const ys = (list(y) || "").split(",").map((s) => s.trim()).filter(Boolean);
  const claimed = typeof binding === "string" && binding !== "" && typeof x === "string" && x !== "" && ys.length > 0;
  const field = claimed ? x : selects;
  const fmtName = format || valueFormat;

  const [off, setOff] = React.useState(highlight === "off");
  React.useLayoutEffect(() => {
    const el = outer.current;
    setOff(highlight === "off" || !!(el && el.closest && el.closest('[data-tb-highlight="off"]')));
  }, [highlight]);
  const [modeTick, setModeTick] = React.useState(0);
  React.useEffect(() => (theme === "auto" ? onModeChange(() => setModeTick((n) => n + 1)) : undefined), [theme]);

  const keep = off ? [] : (claimed ? [x, series] : [selects]).filter(Boolean);
  const rows = useBinding(binding, keep);
  const selection = useSelection();
  const stamped = React.useMemo(() => (binding && tb() ? tb().data(binding) : []), [binding]);

  const resolved = React.useMemo(() => {
    const over = typeof option === "function" ? option(rows) : option;
    const xSet = off ? null : picked(selection, field);
    if (!claimed) return dimOption(over || {}, xSet);
    const palette = theme === "auto" ? (echartsTheme().color || null) : null;
    const base = optionFromRows({ type, rows, stamped, x, ys, series, format: fmtName, unit, stack,
      palette, xSet, sSet: off ? null : picked(selection, series) });
    return over ? mergeOption(base, withoutData(over)) : base;
  }, [rows, stamped, selection, option, off, claimed, type, x, ys.join(","), series, fmtName, unit,
      stack, field, theme, modeTick]);

  const latest = React.useRef(resolved);
  latest.current = resolved;
  const handlers = React.useRef(onEvents);
  handlers.current = onEvents;
  const select = React.useRef(null);
  select.current = field ? (params) => {
    const value = onSelect ? onSelect(params) : params && params.name;
    if (value === null || value === undefined || value === "") return;
    const ev = params && params.event && params.event.event;
    if (tb() && tb().pick) tb().pick(field, String(value), ev);
  } : null;

  const full = (opt) => {
    const o = opt || {};
    if (o.aria !== undefined) return o;
    return { ...o, aria: { enabled: true,
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
    const offMode = auto ? onModeChange(() => {
      const next = echartsTheme();
      if (JSON.stringify(next) === JSON.stringify(applied)) return;
      applied = next;
      c.setTheme(next);
    }) : () => {};
    c.on("click", (p) => { if (select.current) select.current(p); });
    setReady((n) => n + 1);
    return () => { offMode(); if (ro) ro.disconnect(); c.dispose(); chart.current = null; };
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

  // The claim: the same element the kit's <Chart> renders (app_lane.py reads
  // it from the source), drawn by ECharts instead of the runtime.
  const claim = claimed ? {
    id: id || figureId("chart", binding, ys.join(",")),
    "data-tb-figure": "chart", "data-tb-binding": binding, "data-tb-type": kitChartType(type),
    "data-tb-echart-type": type || "bar", "data-tb-x": x, "data-tb-y": ys.join(","),
    "data-tb-color": series, "data-tb-value-format": fmtName, "data-tb-unit": unit,
    "data-tb-stack": flag(stack), "data-tb-engine": "app",
  } : { id, "data-tb-computed": "" };
  return (
    <div ref={outer} className={className} style={style} data-tb-highlight={highlight} {...claim}>
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

/** The masthead that opens the page: an optional mark, a kicker, the title
 * (a string, or text with <Value> figures in it), the standfirst (children),
 * and a meta line with the period the numbers cover, when the file was built
 * and the verdict chip, both filled by the runtime from the file itself.
 * The kicker defaults to the model's label; an explicit one wins, and
 * kicker={null} shows none.
 * `period` is presentation ("Q3 2026"); the title's own numbers are figures.
 * Other props (data-tb-title="center|banner|nav") go on the <header>. */
export function Masthead({ title, kicker, period, mark, className, children, ...rest }) {
  useHydrate();
  const shown = kicker === undefined ? modelKicker() : kicker;
  return (
    <header {...rest} className={["tb-masthead", className || ""].join(" ").trim()}>
      <div className="tb-masthead-mark">{mark}</div>
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
