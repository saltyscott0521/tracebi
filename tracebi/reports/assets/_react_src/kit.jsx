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

/** The stamped rows of one report.json binding (copies; never re-queried). */
export function useBinding(name) {
  return React.useMemo(() => (tb() ? tb().data(name) : []), [name]);
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

export function Kpi({ binding, cell, format, label, context, lead, id, className, children, ...rest }) {
  useHydrate();
  const cls = ["tb-kpi", lead ? "tb-kpi--lead" : "", className || ""].filter(Boolean).join(" ");
  return (
    <div {...rest} className={cls} id={id || figureId("value", binding, cell)}
      data-tb-figure="value" data-tb-binding={binding} data-tb-cell={cell}
      data-tb-format={format}>
      {label != null && <span className="tb-kpi-label">{label}</span>}
      <span className="tb-kpi-value" />
      {context != null && <span className="tb-kpi-context">{context}</span>}
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

export function Table({ binding, columns, labels, formats, sort, bars, totals, rows, id, className }) {
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
        data-tb-rows={rows === undefined ? undefined : String(rows)} />
    </div>
  );
}

/** A filter on one binding's column — or, with no binding, on the whole
 * page: every binding that has the column. It chooses rows; KPIs stay the
 * stamped totals. */
export function Filter({ binding, column, label, className }) {
  useHydrate();
  const select = <select data-tb-filter="" data-tb-binding={binding || "*"} data-tb-column={column} />;
  return label ? <label className={className}>{label} {select}</label> : select;
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
