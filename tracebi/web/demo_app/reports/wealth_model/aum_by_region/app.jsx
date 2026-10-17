// AUM by Region: holdings market value, aggregated by the region of the branch
// that manages the account. Every number is a kit figure over the wealth
// model's declared measures, so the receipt names it.
import { Masthead, Footer, Kpi, Value, Chart, Table, Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead kicker="Wealth" title="Assets under management, by region">
          Market value by the branch that manages the account.
        </Masthead>

        <p className="tb-lede">
          <Value binding="top_region" cell="dim_branch.region" /> manages the most, at{" "}
          <Value binding="top_region" cell="market_value" format="currency_compact" /> of{" "}
          <Value binding="totals" cell="market_value" format="currency_compact" />.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="totals" cell="market_value" format="currency_compact"
               label="Assets under management" context="market value, all regions" id="kpi-aum" />
          <Kpi binding="totals" cell="unrealized_gain" format="currency_compact"
               label="Unrealized gain" context="market value less cost" id="kpi-gain" />
          <Kpi binding="totals" cell="gain_pct" label="Gain on cost" id="kpi-gain-pct" />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <section className="tb-card lg:col-span-2">
            <h2>Market value by region</h2>
            <p className="tb-note">Largest first.</p>
            <Chart binding="by_region" type="barh" x="dim_branch.region" y="market_value"
                   valueFormat="currency_compact" />
          </section>
          <section className="tb-card">
            <h2>By region</h2>
            <div className="mb-3"><Download binding="by_region" /></div>
            <Table binding="by_region" bars="market_value"
                   columns={["dim_branch.region", "market_value", "gain_pct"]}
                   labels={{ "dim_branch.region": "Region", gain_pct: "Gain" }}
                   formats={{ market_value: "currency_compact" }} />
          </section>
        </div>
        <Footer />
      </main>
    </div>
  );
}
