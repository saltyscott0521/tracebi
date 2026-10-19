// app.jsx: this report's page, a React app (the React lane). Numbers shown
// through the tracebi kit (<Kpi>, <Value>, <Chart>, <Table>) carry a trace:
// the build reads their binding / cell / x / y as claims, so keep those literal
// strings. A number your own code computes is the app's presentation, not a
// checked figure. Colours: bg-page bg-card bg-surface text-ink text-muted
// border-rule bg-accent follow the page's theme and mode.
// The kit and patterns: docs/reference/app-jsx.md.
import { useEffect, useState } from "react";
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Search, Download,
         SelectionBar, useBinding } from "tracebi";

// One value in view: "Midwest led with $4,846 of the $4,846" compares a region
// with itself, so a sentence that compares has a one-value form. The count is
// a table's current row count (tracebi.result), as built its stamped rows.
function useRowsInView(binding, tableId) {
  const built = useBinding(binding).length;
  const [rows, setRows] = useState(built);
  useEffect(() => {
    const read = () => {
      const now = window.tracebi.result(tableId);
      setRows(now && now.rows ? now.rows.length : built);
    };
    read();
    return window.tracebi.onSelection(read);
  }, [binding, tableId, built]);
  return rows;
}

export default function App() {
  const regions = useRowsInView("region_detail", "tbl-regions");
  return (
    <div className="min-h-screen bg-page text-ink">
      {/* tb-page is the page measure (1,200px); space-y-8 the rhythm between sections. */}
      <main className="tb-page space-y-8 px-6 py-8">
        {/* The masthead: what this page is, the period its numbers cover, and when
            it was built with the verdict chip (both from the file's trace). The
            kicker above the title is the model's label unless you pass kicker="…". */}
        <Masthead title="Sample Dashboard" period="Every order date">
          Revenue, orders and units across every region.
        </Masthead>

        {/* A page filter: no binding, so it cuts the whole page, and every
            figure follows it. The page reruns each binding's own query over the
            data the file carries, so a figure's number is only ever a query
            result; the trace says which figures were recomputed here. */}
        <div className="flex flex-wrap items-center gap-2">
          <Filter column="dim_region.region" label="Region" />
        </div>
        {/* What the reader picked: one chip per value, each with a ×, Clear and
            "Download what I see". A click on a bar selects too. Hidden as built. */}
        <SelectionBar />

        {/* Lead with the answer: one sentence, its numbers bound. Never type one in. */}
        <p className="tb-lede">
          <Value binding="top_region" cell="dim_region.region" id="val-top-region" />
          {regions === 1 ? " is the only region in view, with " : " led with "}
          <Value binding="top_region" cell="revenue" format="currency0" id="val-top-revenue" />
          <span hidden={regions === 1}> of the{" "}
            <Value binding="kpis" cell="revenue" format="currency0" id="val-revenue-inline" /></span>{" "}
          in revenue.
        </p>

        {/* One KPI strip: the lead number larger, then what explains it. */}
        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="revenue" format="currency0" label="Revenue"
               context="the regions picked, every order date" id="kpi-revenue" />
          <Kpi binding="kpis" cell="orders" format="comma" label="Orders"
               context="count of orders in the sink" id="kpi-orders" />
          <Kpi binding="kpis" cell="units" format="comma" label="Units"
               context="units on those orders" id="kpi-units" />
          {/* A delta: a stamped change shown with its arrow, sign and colour —
              here a report-level measure (report.json "measures"), large orders
              less small. deltaGood says which way is good. No comparison
              measure, no delta: never compute one here. */}
          <Kpi binding="split" cell="big_orders" format="currency0" label="Large orders"
               deltaBinding="split" deltaCell="big_minus_small" deltaFormat="currency0"
               deltaGood="up" context="vs small orders, calculated in this report"
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
            {/* Search narrows the rows shown and computes nothing. The CSV is
                the stamped rows, verbatim. */}
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Search binding="region_detail" placeholder="Find a region…" />
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
