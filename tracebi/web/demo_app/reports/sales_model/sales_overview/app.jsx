// Sales Overview: orders joined to customers through the sales model's
// declared relationship. Every number is a kit figure, so its trace names it.
import { useEffect, useState } from "react";
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Range, SelectionBar,
         Download, useBinding } from "tracebi";

// One value in view: "Midwest leads with $52,994 of the $52,994" compares a
// region with itself, so the lede has a one-region form. The count is the
// region table's current row count (tracebi.result), as built its stamped rows.
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
  const regions = useRowsInView("region_detail", "tbl-region-detail");
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead title="Sales overview">
          Revenue, units and cost by region and customer segment. Nothing here is typed in.
        </Masthead>

        {/* Page controls (no binding): every figure below recomputes for what
            is picked, from the data this file carries. The range is over each
            order's own revenue, so the page keeps one row per order. */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <Filter column="dim_customer.region" label="Region" />
          <Filter column="dim_customer.segment" label="Segment" />
          <Range column="revenue" label="Order revenue" />
        </div>
        <SelectionBar />

        <p className="tb-lede" hidden={regions === 1}>
          <Value binding="top_region" cell="dim_customer.region" /> leads with{" "}
          <Value binding="top_region" cell="revenue" format="currency0" /> of the{" "}
          <Value binding="totals" cell="revenue" format="currency0" /> booked.
        </p>
        <p className="tb-lede" hidden={regions !== 1}>
          <Value binding="top_region" cell="dim_customer.region" id="val-only-region" /> is the
          only region in view, with{" "}
          <Value binding="totals" cell="revenue" format="currency0" id="val-only-revenue" /> booked.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="totals" cell="revenue" format="currency0" label="Revenue"
               context="the orders in view" id="kpi-revenue" />
          <Kpi binding="totals" cell="qty" format="comma" label="Units" id="kpi-units" />
          <Kpi binding="totals" cell="cost" format="currency0" label="Cost" id="kpi-cost" />
        </div>

        <div className="tb-grid">
          <section className="tb-card tb-span-6">
            <h2>Revenue by region</h2>
            <p className="tb-note">Largest first. Click a bar to select its region.</p>
            <Chart binding="by_region" type="barh" x="dim_customer.region" y="revenue"
                   valueFormat="currency_compact" />
          </section>
          <section className="tb-card tb-span-6">
            <h2>Region detail</h2>
            <p className="tb-note">The regions in view.</p>
            <Table binding="region_detail" id="tbl-region-detail"
                   labels={{ "dim_customer.region": "Region", qty: "Units" }}
                   formats={{ revenue: "currency0", qty: "comma" }} />
          </section>
        </div>

        {/* Four columns: the full width, so none runs past the card's edge. */}
        <div className="tb-grid">
          <section className="tb-card tb-span-12">
            <h2>By customer segment</h2>
            <p className="tb-note">The CSV is the stamped rows, verbatim.</p>
            <div className="mb-3"><Download binding="by_segment" /></div>
            <Table binding="by_segment" bars="revenue"
                   labels={{ "dim_customer.segment": "Segment", qty: "Units" }}
                   formats={{ revenue: "currency0", qty: "comma", cost: "currency0" }} />
          </section>
        </div>
        <Footer />
      </main>
    </div>
  );
}
