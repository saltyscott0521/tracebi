// Portfolio Dashboard: the whole book on one screen, an app (the React lane).
// Every number is a kit figure (<Kpi>, <Chart>, <Table>) with a literal
// binding and cell, so the build records it and the receipt names it. The
// search and the sector filter choose which stamped rows show; they never
// compute a number.
import { Kpi, Chart, Table, Filter, Search, Download, Built } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="mx-auto max-w-6xl space-y-5 px-6 py-8">
        <header className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Direct lending: portfolio book</h1>
            <p className="text-sm text-muted">Three funds, cleaned from a Schedule-of-Investments
              export. Every number is a query against the model.</p>
          </div>
          <Built className="text-xs text-muted" />
        </header>

        <div className="tb-grid">
          <Kpi lead binding="totals" cell="fair_value" format="currency_compact"
               label="Fair value" context="administrator marks" id="kpi-fair-value" />
          <Kpi binding="totals" cell="positions" label="Positions" id="kpi-positions" />
          <Kpi binding="totals" cell="unrealized" format="currency_compact"
               label="Unrealized" context="fair value less cost" id="kpi-unrealized" />
          <Kpi binding="totals" cell="mark" label="Portfolio mark"
               context="fair value / cost" id="kpi-mark" />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <section className="tb-card lg:col-span-2">
            <h2>Fair value by sector</h2>
            <p className="tb-note">Largest first.</p>
            <Chart binding="by_sector" type="barh" x="dim_issuer.sector" y="fair_value"
                   valueFormat="currency_compact" />
          </section>
          <section className="tb-card">
            <h2>By fund</h2>
            <p className="tb-note">Fair value each fund holds.</p>
            <Chart binding="by_fund" type="barh" x="dim_fund.fund" y="fair_value"
                   valueFormat="currency_compact" />
          </section>
        </div>

        <section className="tb-card">
          <h2>Holdings by issuer</h2>
          <p className="tb-note">Every issuer, largest first. The total row is the stamped
            total, not a sum of the rows shown.</p>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Search binding="holdings" placeholder="Find an issuer…" />
            <Filter binding="holdings" column="dim_issuer.sector" label="Sector" />
            <Download binding="holdings" />
          </div>
          <Table binding="holdings" id="holdings-table" sort rows="all" bars="fair_value"
                 totals="holdings_totals"
                 columns={["dim_issuer.issuer", "dim_issuer.sector", "fair_value",
                           "cost_basis", "unrealized", "mark", "positions"]}
                 labels={{ "dim_issuer.issuer": "Issuer", "dim_issuer.sector": "Sector",
                           "cost_basis": "Cost" }} />
        </section>
      </main>
    </div>
  );
}
