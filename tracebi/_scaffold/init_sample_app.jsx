// app.jsx: this report's page, a React app (the React lane). Numbers shown
// through the tracebi kit (<Kpi>, <Value>, <Chart>, <Table>) carry the receipt:
// the build reads their binding / cell / x / y as claims, so keep those literal
// strings. A number your own code computes is the app's presentation, not a
// checked figure. Colours: bg-page bg-card bg-surface text-ink text-muted
// border-rule bg-accent follow the page's theme and mode.
// The kit and patterns: docs/reference/app-jsx.md.
import { Kpi, Value, Chart, Table, Filter, Search, Download, Built } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="mx-auto max-w-6xl space-y-5 px-6 py-8">
        {/* The title: what this page is, and when it was built (from its receipt). */}
        <header className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Orders — Sample Dashboard</h1>
            <p className="text-sm text-muted">Revenue, orders and units across every region.</p>
          </div>
          <Built className="text-xs text-muted" />
        </header>

        {/* Lead with the answer: one sentence, its numbers bound. Never type one in. */}
        <p className="tb-lede">
          <Value binding="top_region" cell="dim_region.region" id="val-top-region" /> led every
          region with{" "}
          <Value binding="top_region" cell="revenue" format="currency0" id="val-top-revenue" /> of
          the <Value binding="kpis" cell="revenue" format="currency0" id="val-revenue-inline" /> in
          revenue.
        </p>

        {/* One KPI strip: the lead number twice as wide, then what explains it. */}
        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="revenue" format="currency0" label="Revenue"
               context="all regions, all order dates" id="kpi-revenue" />
          <Kpi binding="kpis" cell="orders" format="comma" label="Orders"
               context="count of orders in the sink" id="kpi-orders" />
          <Kpi binding="kpis" cell="units" format="comma" label="Units"
               context="units on those orders" id="kpi-units" />
          {/* A report-level measure (report.json "measures"): stamped like the rest. */}
          <Kpi binding="split" cell="big_minus_small" format="currency0"
               label="Large orders less small" context="calculated in this report, not the model"
               id="kpi-split" />
        </div>

        {/* A wide panel beside a narrow one; one column on a phone. */}
        <div className="grid gap-4 lg:grid-cols-3">
          <section className="tb-card lg:col-span-2">
            <h2>Revenue by region</h2>
            <p className="tb-note">Ranked by revenue, largest first.</p>
            <Chart binding="by_region" type="barh" x="dim_region.region" y="revenue"
                   valueFormat="currency_compact" id="chart-by-region" />
          </section>
          <section className="tb-card">
            <h2>Region detail</h2>
            {/* Controls choose which stamped rows show; they never compute a number.
                The CSV is the stamped rows, verbatim. */}
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Search binding="region_detail" placeholder="Find a region…" />
              <Filter binding="region_detail" column="dim_region.region" label="Region" />
              <Download binding="region_detail" />
            </div>
            <Table binding="region_detail" id="tbl-regions" sort bars="revenue"
                   labels={{ "dim_region.region": "Region" }}
                   formats={{ revenue: "currency0" }} />
          </section>
        </div>
      </main>
    </div>
  );
}
