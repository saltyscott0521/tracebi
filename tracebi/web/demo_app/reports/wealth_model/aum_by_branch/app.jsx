// AUM by Branch & Asset Class: the custom-styled demo, an app. Its look is
// style.css (fonts, the hero band, colours) on the system's frame; its
// numbers are kit figures, so the trace names every one. Net new assets is
// this report's own calculation (report.json "measures"), stamped like the rest.
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <div className="wm-hero">
        <Masthead className="wm-hero-inner"
          title={<>Where the book sits, <em>branch by branch.</em></>}>
          Assets under management across six branches and four asset classes. The book
          stands at{" "}
          <Value binding="at_a_glance" cell="market_value" format="currency_compact"
                 id="val-aum-inline" />; every number on this page is a live query against the
          wealth model, with its fingerprint in its <strong>trace</strong>.
        </Masthead>
      </div>

      <main className="tb-page space-y-8 px-6 py-8">
        {/* A page filter (no binding): every figure recomputes for the region
            picked; one the region cannot reach says so. */}
        <Filter column="dim_branch.region" label="Region" />
        <div className="tb-grid wm-kpis">
          <Kpi lead binding="at_a_glance" cell="market_value" format="currency_compact"
               label="Total AUM" context="market value, every branch" id="kpi-aum" />
          <Kpi binding="at_a_glance" cell="unrealized_gain" format="currency_compact"
               label="Unrealized gain" context="market value less cost" id="kpi-gain" />
          <Kpi binding="at_a_glance" cell="gain_pct" format="percent" label="Gain on cost"
               context="a ratio of totals" id="kpi-gain-pct" />
        </div>

        <div className="tb-grid">
          <section className="tb-card tb-span-8">
            <h2>AUM by branch</h2>
            <Chart binding="by_branch" type="barh" x="dim_branch.branch" y="market_value"
                   valueFormat="currency_compact" id="chart-branch" />
          </section>
          <section className="tb-card tb-span-4">
            <h2>AUM by asset class</h2>
            <Chart binding="by_asset_class" type="pie" x="dim_product.asset_class"
                   y="market_value" valueFormat="currency_compact" id="chart-asset" />
          </section>
        </div>

        <section className="tb-card">
          <h2>Net new assets by branch</h2>
          <p className="tb-note">Purchases less sales, from the activity log. This report
            calculates it itself; the shared model does not carry it.</p>
          <Table binding="net_new_by_branch" id="tbl-net-new" sort bars="net_new_assets"
                 columns={["dim_branch.branch", "purchases", "sales", "net_new_assets"]}
                 labels={{ "dim_branch.branch": "Branch", net_new_assets: "Net new assets" }}
                 formats={{ purchases: "currency0", sales: "currency0",
                            net_new_assets: "currency0" }} />
        </section>

        <div className="tb-grid">
          <section className="tb-card tb-span-6">
            <h2>Branch summary</h2>
            <div className="mb-3"><Download binding="branch_summary" /></div>
            <Table binding="branch_summary" id="tbl-branch" sort totals="at_a_glance"
                   columns={["dim_branch.branch", "dim_branch.region", "market_value",
                             "unrealized_gain", "gain_pct"]}
                   labels={{ "dim_branch.branch": "Branch", "dim_branch.region": "Region",
                             market_value: "AUM", unrealized_gain: "Gain", gain_pct: "On cost" }}
                   formats={{ market_value: "currency_compact", unrealized_gain: "currency_compact",
                              gain_pct: "percent" }} />
          </section>
          <section className="tb-card tb-span-6">
            <h2>Asset class breakdown</h2>
            <Table binding="by_asset_class" id="tbl-asset" sort totals="at_a_glance"
                   labels={{ "dim_product.asset_class": "Asset class", market_value: "AUM",
                             unrealized_gain: "Unrealized gain" }}
                   formats={{ market_value: "currency_compact",
                              unrealized_gain: "currency_compact" }} />
          </section>
        </div>

        <Footer />
      </main>
    </div>
  );
}
