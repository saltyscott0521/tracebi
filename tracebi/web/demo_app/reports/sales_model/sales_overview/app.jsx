// Sales Overview: orders joined to customers through the sales model's
// declared relationship. Every number is a kit figure, so the receipt names it.
import { Kpi, Value, Chart, Table, Download, Built } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="mx-auto max-w-6xl space-y-5 px-6 py-8">
        <header className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Sales overview</h1>
            <p className="text-sm text-muted">Revenue, units and cost by region and customer
              segment. Nothing here is typed in.</p>
          </div>
          <Built className="text-xs text-muted" />
        </header>

        <p className="tb-lede">
          <Value binding="top_region" cell="dim_customer.region" /> leads with{" "}
          <Value binding="top_region" cell="revenue" format="currency0" /> of the{" "}
          <Value binding="totals" cell="revenue" format="currency0" /> booked.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="totals" cell="revenue" format="currency0" label="Revenue"
               context="all orders, all regions" id="kpi-revenue" />
          <Kpi binding="totals" cell="qty" format="comma" label="Units" id="kpi-units" />
          <Kpi binding="totals" cell="cost" format="currency0" label="Cost" id="kpi-cost" />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <section className="tb-card lg:col-span-2">
            <h2>Revenue by region</h2>
            <p className="tb-note">Largest first.</p>
            <Chart binding="by_region" type="barh" x="dim_customer.region" y="revenue"
                   valueFormat="currency_compact" />
          </section>
          <section className="tb-card">
            <h2>By customer segment</h2>
            <p className="tb-note">The CSV is the stamped rows, verbatim.</p>
            <div className="mb-3"><Download binding="by_segment" /></div>
            <Table binding="by_segment" bars="revenue"
                   labels={{ "dim_customer.segment": "Segment", qty: "Units" }}
                   formats={{ revenue: "currency0", qty: "comma", cost: "currency0" }} />
          </section>
        </div>
      </main>
    </div>
  );
}
