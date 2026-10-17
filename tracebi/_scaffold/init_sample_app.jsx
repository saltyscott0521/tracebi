// app.jsx: this report's page, a React app (the React lane). Numbers shown
// through the tracebi kit (<Kpi>, <Value>, <Chart>, <Table>) carry the receipt:
// the build reads their binding / cell / x / y as claims, so keep those literal
// strings. A number your own code computes is the app's presentation, not a
// checked figure. Colours: bg-page bg-card bg-surface text-ink text-muted
// border-rule bg-accent follow the page's theme and mode.
// The kit and patterns: docs/reference/app-jsx.md.
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Search, Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      {/* tb-page is the page measure (1,200px); space-y-8 the rhythm between sections. */}
      <main className="tb-page space-y-8 px-6 py-8">
        {/* The masthead: what this page is, the period its numbers cover, and when
            it was built with the verdict chip (both from the file's receipt). */}
        <Masthead kicker="Orders" title="Sample Dashboard" period="Every order date">
          Revenue, orders and units across every region.
        </Masthead>

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

        {/* The 12-column grid: a wide panel (8) beside a narrow one (4); one
            column on a phone. */}
        <div className="tb-grid">
          <section className="tb-card tb-span-8">
            <h2>Revenue by region</h2>
            <p className="tb-note">Ranked by revenue, largest first.</p>
            <Chart binding="by_region" type="barh" x="dim_region.region" y="revenue"
                   valueFormat="currency_compact" id="chart-by-region" />
          </section>
          <section className="tb-card tb-span-4">
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
        {/* The footer the build writes: one line on how these numbers were made. */}
        <Footer />
      </main>
    </div>
  );
}
