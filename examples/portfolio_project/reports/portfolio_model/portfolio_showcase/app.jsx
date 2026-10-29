// Portfolio Showcase: the app lane's kitchen sink, kept as a product.
//
// Every number on this page is a kit figure (<Kpi>, <Value>, <Chart>, <Spark>,
// <EChart>, <Table>) with a literal binding and cell, so the build records it
// as a claim, refuses a binding or column that does not exist, and the trace
// names it. Every figure is live: the sidebar's filters, the ranges, a click
// on a bar, slice, point, cell or legend entry, and a click on a table row all
// write the page's one selection, and each figure re-runs its own query over
// the data this file carries. The KPI strip sits above every view, so every
// gesture moves it; the selection bar says what is picked.
//
// What the page draws for itself is said so: the fund-by-sector heatmap is an
// option-only <EChart> whose cells this page lays out from a binding's rows,
// so it carries data-tb-computed and is not a claim. The one python-derived
// figure (report.py, the escape hatch) is fixed at build, never green, and
// says so where it is read.
import { useMemo } from "react";
import { LayoutDashboard, Table2, Target, ShieldCheck, ArrowLeftRight,
         Layers } from "lucide-react";
import { Masthead, Footer, Kpi, Value, Chart, Spark, EChart, Table, Filter, Range,
         Search, Download, SelectionBar, Segmented, useBinding, useSelection,
         useUrlState, usePrinting, chartTokens } from "tracebi";

const VIEWS = [
  { name: "Overview", icon: LayoutDashboard, about: "Where the book sits" },
  { name: "Holdings", icon: Table2, about: "Every position, searchable" },
  { name: "Concentration", icon: Target, about: "How much rides on a few" },
  { name: "Credit", icon: ShieldCheck, about: "Ratings, watch list, spread" },
  { name: "Cash flows", icon: ArrowLeftRight, about: "What came in, what went out" },
];

// A panel: the card, its title, an optional note, the figure.
function Panel({ title, note, span, children, aside }) {
  return (
    <section className={"tb-card" + (span ? ` ${span}` : "")}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="!m-0 text-[0.95rem] font-semibold tracking-tight">{title}</h2>
          {note && <p className="tb-note !mb-0 !mt-1">{note}</p>}
        </div>
        {aside && <div className="shrink-0 whitespace-nowrap">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

// ── Overview ────────────────────────────────────────────────────────────────

function Overview() {
  // Printed, the pie is shorter (a bar chart sizes itself by its bars), so
  // the first row fits on the first page under the KPI strip.
  const printing = usePrinting();
  return (
    <>
      <div className="tb-grid">
        <Panel span="tb-span-8" title="Fair value by sector"
          note="Largest first. Click a bar to select its sector; shift-click adds one.">
          <Chart binding="by_sector" type="barh" x="dim_issuer.sector" y="fair_value"
                 valueFormat="currency_compact" id="chart-sector" height={300} />
        </Panel>
        <Panel span="tb-span-4" title="By fund" note="Each fund's share of the book. A slice selects its fund.">
          <Chart binding="by_fund" type="pie" x="dim_fund.fund" y="fair_value"
                 valueFormat="currency_compact" id="chart-fund" height={printing ? 220 : 300} />
        </Panel>
      </div>
      {/* Small multiples: one panel per fund on one shared scale, each fund's
          largest sector labelled with its own row's value. highlight="off":
          a sector picked narrows these panels instead of dimming the rest.
          Printed, the panels sit two across, too narrow for upright sector
          names, and a column chart labels only the panels with none below:
          as bars across, every panel carries its names, so all are one
          height, and tall enough to name every sector. */}
      <Panel title="Each fund's book, sector by sector"
        note="One panel per fund, one scale, so the panels compare. Each fund's largest sector is labelled.">
        <Chart binding="fund_sector" type={printing ? "barh" : "bar"} x="dim_issuer.sector" y="fair_value"
               facet="dim_fund.fund" mark="max" highlight="off" yTitle="Fair value"
               valueFormat="compact" id="chart-fund-sector"
               height={printing ? 440 : undefined} />
      </Panel>
      <div className="tb-grid">
        <Panel span="tb-span-6" title="Where each fund's money sits"
          note="Fund by sector, darker is more. Laid out by this page from the fund-by-sector rows: live, not a checked figure. Click a cell to select its sector.">
          <FundSectorHeatmap />
        </Panel>
        <Panel span="tb-span-6" title="Unrealized gain and loss by sector"
          note="Fair value less cost. A bar left of zero is a sector marked under what was paid.">
          <Chart binding="by_sector" type="barh" x="dim_issuer.sector" y="unrealized"
                 valueFormat="currency_compact" id="chart-sector-unrealized" height={280} />
        </Panel>
      </div>
    </>
  );
}

// An option-only <EChart>: the cells are this page's own layout of the
// fund_sector rows (re-run under the selection by useBinding), so it carries
// data-tb-computed. It draws in the house theme; the colour ramp is read from
// the page's chart tokens, so a theme or the workspace's brand restyles it.
function FundSectorHeatmap() {
  const rows = useBinding("fund_sector", "dim_issuer.sector");
  const printing = usePrinting();
  const option = useMemo(() => {
    const k = chartTokens();
    const sectors = [...new Set(rows.map((r) => r["dim_issuer.sector"]))].sort();
    const funds = [...new Set(rows.map((r) => r["dim_fund.fund"]))].sort().reverse();
    const values = rows.map((r) => Number(r.fair_value) || 0);
    return {
      tooltip: { trigger: "item",
                 valueFormatter: (v) => (Array.isArray(v) ? window.tracebi.format(v[2], "currency_compact") : v) },
      grid: { left: 8, right: 8, top: 8, bottom: 52, containLabel: true },
      xAxis: { type: "category", data: sectors, splitArea: { show: false },
               axisLabel: { interval: 0, rotate: 30 } },
      yAxis: { type: "category", data: funds, axisLabel: { width: 120, overflow: "truncate" } },
      visualMap: { show: false, min: 0, max: Math.max(1, ...values),
                   inRange: { color: [k.card, k.accent] } },
      series: [{
        type: "heatmap",
        itemStyle: { borderColor: k.card, borderWidth: 3, borderRadius: 4 },
        // Each cell's value written in it where there is room; on a phone or
        // a printed page the cells are too narrow and the tooltip reads it.
        label: { show: !printing && window.innerWidth >= 640, formatter: (p) => window.tracebi.fmt(p.value[2], "compact"),
                 fontSize: 11, fontFamily: k.num },
        data: rows.map((r) => ({
          name: r["dim_issuer.sector"],
          value: [sectors.indexOf(r["dim_issuer.sector"]), funds.indexOf(r["dim_fund.fund"]),
                  Number(r.fair_value) || 0],
        })),
      }],
    };
  }, [rows, printing]);
  return (
    <EChart option={option} selects="dim_issuer.sector" height={280} id="ech-fund-sector"
            ariaLabel="Fair value by fund and sector, as a heatmap" />
  );
}

// ── Holdings ────────────────────────────────────────────────────────────────

// A scatter's two axes are two measures in two units, and a chart's value
// format is one: so these scatters take no value format (the tooltip reads
// each column in the format the model declares) and restyle their tick labels
// through option, which styles a checked chart and never re-sources it.
function scatterTicks(xFormat) {
  const fmt = (f) => (v) => window.tracebi.format(v, f);
  return { xAxis: { axisLabel: { formatter: fmt(xFormat) } },
           // The axis title clears the longer "105.0%" ticks.
           yAxis: { axisLabel: { formatter: fmt("percent") }, nameGap: 52 } };
}

function Holdings() {
  return (
    <>
      <Panel title="Every holding"
        note="One row per issuer. Search narrows the rows shown and computes nothing; the filters, the range and a click on a row recompute every figure. The total row is the model's own total for what is picked, not a sum of the rows shown. The CSV is the stamped data, verbatim."
        aside={<Download binding="holdings_detail" />}>
        <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-3">
          <Search binding="holdings_detail" placeholder="Find an issuer…" />
          <Range column="fair_value" label="Holding fair value" />
        </div>
        <Table binding="holdings_detail" id="tbl-detail" sort rows="all" bars="fair_value"
               selectRows="dim_issuer.issuer" totals="holdings_total"
               columns={["dim_issuer.issuer", "dim_issuer.sector", "dim_rating.rating", "fair_value",
                         "cost_basis", "unrealized", "mark", "wtd_spread_bps"]}
               labels={{ "dim_issuer.issuer": "Issuer", "dim_issuer.sector": "Sector",
                         "dim_rating.rating": "Rating", "cost_basis": "Cost",
                         "mark": "Mark", "wtd_spread_bps": "Spread, bps" }}
               formats={{ "fair_value": "currency0", "cost_basis": "currency0",
                          "unrealized": "currency0", "mark": "percent",
                          "wtd_spread_bps": "comma" }} />
      </Panel>
      <div className="tb-grid">
        <Panel span="tb-span-6" title="Size against mark"
          note="Each issuer: its fair value across, its mark up. Click a point to select it.">
          <Chart binding="issuer_fv" type="scatter" x="fair_value" y="mark"
                 xTitle="Fair value" yTitle="Mark (fair value ÷ cost)" id="chart-size-mark"
                 height={300} option={scatterTicks("currency_compact")} />
        </Panel>
        <Panel span="tb-span-6" title="Spread against mark"
          note="The wider an issuer's spread, the more the market wants for holding it.">
          <Chart binding="issuer_fv" type="scatter" x="wtd_spread_bps" y="mark"
                 xTitle="Spread, bps" yTitle="Mark" id="chart-spread-mark" height={300}
                 option={scatterTicks("comma")} />
        </Panel>
      </div>
    </>
  );
}

// ── Concentration ───────────────────────────────────────────────────────────

function Concentration() {
  return (
    <>
      <div className="tb-grid">
        <Panel span="tb-span-8" title="Every issuer, sized by fair value"
          note="A treemap of the binding's own rows (a claim, like any kit chart). Click a cell to select its issuer.">
          {/* binding, x and y literal: ECharts' treemap series, reached
              through the chart engine's option builder, and checked. */}
          <EChart binding="issuer_fv" type="treemap" x="dim_issuer.issuer" y="fair_value"
                  format="currency_compact" id="ech-issuer-treemap" height={500}
                  ariaLabel="Fair value by issuer, as a treemap" />
        </Panel>
        <Panel span="tb-span-4" title="The largest eight"
          note="Each one's share of the whole book. Click a row to select the issuer.">
          <Table binding="top_issuers" id="tbl-top" selectRows bars="fv_share" rows="all"
                 columns={["dim_issuer.issuer", "fv_share", "mark"]}
                 labels={{ "dim_issuer.issuer": "Issuer", "fv_share": "Share" }} />
        </Panel>
      </div>
      <div className="tb-grid">
        <Panel span="tb-span-8" title="Cumulative share, issuers by rank"
          note="Read across: how much of the book the largest issuers hold together.">
          <Chart binding="issuer_curve" type="area" x="fv_rank" y="fv_cum_share"
                 valueFormat="percent" xTitle="Issuers, by rank" mark="last"
                 id="chart-issuer-curve" height={260} />
        </Panel>
        <Panel span="tb-span-4" title="Cumulative share, largest sector first"
          note="Python-derived (report.py), the escape hatch: fixed at build, never re-run, and its trace says so.">
          <Chart binding="concentration" type="line" x="dim_issuer.sector" y="cum_share"
                 valueFormat="percent" id="chart-conc" height={260} />
        </Panel>
      </div>
    </>
  );
}

// ── Credit ──────────────────────────────────────────────────────────────────

function Credit() {
  return (
    <>
      <div className="tb-grid">
        <Kpi binding="kpis" cell="spread_p90" format="comma" label="Spread, 90th percentile"
             context="bps: the wide tail the average hides" id="kpi-spread-p90" />
        <Kpi binding="watched" cell="fair_value" format="currency_compact" label="On the watch list"
             context="fair value the credit team is watching" id="kpi-watched" />
        <Kpi binding="watched" cell="positions" format="comma" label="Watched positions"
             context="loans flagged in the CRM" id="kpi-watched-positions" />
      </div>
      <div className="tb-grid">
        <Panel span="tb-span-6" title="Fair value by CRM rating"
          note="The rating comes from the credit team's CRM, a Postgres source the transform reads (or its snapshot, and the trace says which). Click a bar to select a rating.">
          <Chart binding="by_rating" type="barh" x="dim_rating.rating" y="fair_value"
                 valueFormat="currency_compact" id="chart-rating" height={280} />
        </Panel>
        <Panel span="tb-span-6" title="On the watch list, by rating"
          note="Stacked: what the credit team watches, against what it does not. A legend chip selects its value.">
          <Chart binding="rating_watch" type="bar" x="dim_rating.rating" y="fair_value"
                 color="dim_rating.watch" stack valueFormat="currency_compact"
                 id="chart-rating-watch" height={280} />
        </Panel>
      </div>
      <Panel title="Ratings side by side" note="Click a row to select its rating.">
        <Table binding="by_rating" id="tbl-rating" selectRows sort bars="wtd_spread_bps"
               columns={["dim_rating.rating", "fair_value", "positions", "wtd_spread_bps", "mark"]}
               labels={{ "dim_rating.rating": "Rating", "wtd_spread_bps": "Spread, bps" }}
               formats={{ "fair_value": "currency0", "wtd_spread_bps": "comma", "mark": "percent" }} />
      </Panel>
    </>
  );
}

// ── Cash flows ──────────────────────────────────────────────────────────────

function CashFlows() {
  // Which figure the chart card shows: one literal figure per option, so
  // each keeps its own trace. The choice rides in the URL.
  const [measure, setMeasure] = useUrlState("flows", "Net");
  return (
    <>
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3 print:hidden">
        {/* Flow type reaches only the cash flows: every holdings figure keeps
            its number and says it is not filtered by it. */}
        <Filter column="dim_flow_type.flow_type" label="Flow type" />
        <Range column="dim_date.month" label="Months" />
      </div>
      <div className="tb-grid">
        <Kpi binding="flows" cell="flow_count" format="comma" label="Cash flows"
             context="coupons, drawdowns and repayments" id="kpi-flow-count">
          <Spark binding="flows_by_month" x="dim_date.month" y="flow_count" type="bar"
                 id="spark-flow-count" />
        </Kpi>
        <Kpi binding="flows" cell="net_flow" format="currency_compact" label="Net cash flow"
             context="received less lent out" id="kpi-net-flow-view">
          <Spark binding="flows_by_month" x="dim_date.month" y="net_flow" id="spark-net-flow-view" />
        </Kpi>
      </div>
      <Panel title={measure === "Net" ? "Net cash flow by month" : "Cash flows by month"}
        note="Drag the slider under the chart to zoom: an ECharts tool on a checked chart, which restyles it and never re-sources it."
        aside={<Segmented options={["Net", "Count"]} value={measure} onChange={setMeasure}
                          label="Measure" />}>
        {measure === "Net" ? (
          <EChart binding="flows_by_month" type="line" x="dim_date.month" y="net_flow"
                  format="currency_compact" mark="max" id="ech-flows-month" height={300}
                  annotate={{ "2025-03": "Quarterly coupons begin", "2025-10": "New drawdowns" }}
                  option={{ dataZoom: [{ type: "slider", height: 18, bottom: 6, brushSelect: false }],
                            grid: [{ bottom: 48 }] }} />
        ) : (
          <Chart binding="flows_by_month" type="bar" x="dim_date.month" y="flow_count"
                 id="chart-flows-count" height={300} />
        )}
      </Panel>
      <div className="tb-grid">
        <Panel span="tb-span-4" title="By flow type" note="Interest in, drawdowns out. Click a bar.">
          <Chart binding="flows_by_type" type="bar" x="dim_flow_type.flow_type" y="net_flow"
                 valueFormat="currency_compact" id="chart-flow-type" height={260} />
        </Panel>
        <Panel span="tb-span-8" title="By fund and flow type">
          <Table binding="flows_by_fund" id="tbl-flows" sort bars="flow_count" rows="all"
                 labels={{ "dim_fund.fund": "Fund", "dim_flow_type.flow_type": "Flow type",
                           "flow_count": "Flows" }}
                 formats={{ "net_flow": "currency0", "flow_count": "comma" }} />
        </Panel>
      </div>
    </>
  );
}

const PAGES = { Overview, Holdings, Concentration, Credit, "Cash flows": CashFlows };

// What the reader has picked, in words: the fields, never a number this page
// works out.
function Picked() {
  const sel = useSelection();
  const fields = Object.keys(sel);
  return (
    <p className="m-0 text-xs leading-relaxed text-muted">
      {fields.length ? "Picked: " + fields.map((f) => f.split(".").pop().replace(/_/g, " ")).join(", ")
                     : "Nothing picked: the whole book."}
    </p>
  );
}

function Sidebar({ view, setView }) {
  return (
    <aside className="shrink-0 border-b border-rule bg-card md:min-h-screen md:w-64 md:border-r
                      md:border-b-0 print:hidden">
      <div className="space-y-5 p-4 md:sticky md:top-0 md:max-h-screen md:overflow-y-auto">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent text-on-accent">
            <Layers size={18} />
          </span>
          <div className="min-w-0 leading-tight">
            <p className="m-0 text-sm font-semibold">Portfolio Showcase</p>
            <p className="m-0 text-xs text-muted">The book, one app</p>
          </div>
        </div>
        <nav aria-label="Views" className="-mx-1 flex gap-1 overflow-x-auto md:mx-0 md:flex-col">
          {VIEWS.map(({ name, icon: Icon, about }) => (
            <button key={name} type="button" onClick={() => setView(name)}
              aria-current={view === name ? "page" : undefined}
              className={"group flex shrink-0 items-center gap-3 rounded-lg px-2.5 py-2 text-left " +
                (view === name ? "bg-surface text-ink" : "text-muted hover:bg-surface hover:text-ink")}>
              <Icon size={17} className={view === name ? "text-accent-text" : ""} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{name}</span>
                <span className="hidden text-xs text-muted md:block">{about}</span>
              </span>
            </button>
          ))}
        </nav>
        {/* Page filters: in the sidebar, so what they pick holds on every view. */}
        <div className="space-y-3 border-t border-rule pt-4">
          <p className="m-0 text-xs font-semibold uppercase tracking-wider text-muted">Filter the book</p>
          <div className="grid gap-3 [&_label]:flex [&_label]:flex-col [&_label]:items-stretch [&_label]:text-left
                          [&_label]:gap-1 [&_label]:text-xs [&_label]:font-medium [&_label]:text-muted
                          [&_select]:w-full">
            <Filter column="dim_issuer.sector" label="Sector" />
            <Filter column="dim_fund.fund" label="Fund" multiple />
            <Filter column="dim_rating.rating" label="Rating" multiple />
          </div>
          <Picked />
        </div>
        <p className="m-0 hidden border-t border-rule pt-4 text-xs leading-relaxed text-muted md:block">
          Every number is a query against the model, re-run on this page for what you
          pick. Press Escape to clear. Open the trace from the masthead.
        </p>
      </div>
    </aside>
  );
}

export default function App() {
  // The view lives in the URL (#view=Credit): a shared link opens on it,
  // beside the selection (#sel=).
  const [view, setView] = useUrlState("view", "Overview");
  const View = PAGES[view] || Overview;
  // Printed (Ctrl+P, or the PDF build), the page holds every view.
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink md:flex">
      <Sidebar view={view} setView={setView} />
      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1240px] space-y-6 px-4 py-6 md:px-8 md:py-8">
          <Masthead period="Latest administrator marks"
            title={<><Value binding="top_sector" cell="dim_issuer.sector" id="val-top-sector" /> is
              the largest sector, <Value binding="top_sector" cell="fv_share" format="percent"
              id="val-top-share" /> of the book</>}>
            Three funds' loans, cleaned from a Schedule of Investments and modelled as a
            star schema: <Value binding="kpis" cell="fair_value" format="currency_compact"
            id="val-fv-inline" /> at fair value, marked at <Value binding="kpis" cell="mark"
            format="percent" id="val-mark-inline" /> of cost. The largest single
            borrower, <Value binding="top_issuer" cell="dim_issuer.issuer" id="val-top-issuer" />,
            is <Value binding="top_issuer" cell="fv_share" format="percent" id="val-top-issuer-share" /> of
            it.
          </Masthead>

          {/* The KPI strip is above every view, so every gesture moves it. */}
          <div className="tb-grid max-md:!grid-cols-2
                          md:![grid-template-columns:1.6fr_repeat(4,minmax(0,1fr))]
                          print:![grid-template-columns:1.3fr_repeat(4,minmax(0,1fr))]">
            <Kpi lead className="max-md:col-span-2" binding="kpis" cell="fair_value" format="currency_compact" label="Fair value"
                 deltaBinding="kpis" deltaCell="unrealized" deltaFormat="currency_compact"
                 deltaGood="up" context="vs cost" id="kpi-fv" />
            <Kpi binding="kpis" cell="mark" format="percent" label="Mark"
                 context="fair value per dollar of cost" id="kpi-mark" />
            <Kpi binding="kpis" cell="wtd_spread_bps" format="decimal" label="Spread, bps"
                 context="par-weighted" id="kpi-spread" />
            <Kpi binding="kpis" cell="positions" format="comma" label="Positions"
                 context="loans in view" id="kpi-positions" />
            <Kpi binding="flows" cell="net_flow" format="currency_compact" label="Net cash flow"
                 context="received less lent out" id="kpi-net-flow">
              <Spark binding="flows_by_month" x="dim_date.month" y="net_flow" id="spark-net-flow" />
            </Kpi>
          </div>

          {/* What the reader picked, one chip per value; hidden as built. */}
          <SelectionBar />

          {printing ? (
            VIEWS.map(({ name }) => {
              const Each = PAGES[name];
              return (
                <section key={name} className="space-y-4">
                  <h2 className="text-xl font-semibold tracking-tight print:break-after-avoid">{name}</h2>
                  <Each />
                </section>
              );
            })
          ) : (
            <section className="space-y-4" aria-label={view}>
              <h2 className="sr-only">{view}</h2>
              <View />
            </section>
          )}
          <Footer />
        </div>
      </main>
    </div>
  );
}
