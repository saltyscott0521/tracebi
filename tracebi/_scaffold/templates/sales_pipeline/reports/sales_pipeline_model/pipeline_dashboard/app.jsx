// Sales Pipeline Dashboard: an app (the React lane). Every number is a kit
// figure, so the receipt names it. Open pipeline is the sum of amounts on deals
// still open; win rate is won deals over closed deals, a ratio of totals.
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead kicker="Sales pipeline"
          title={<><Value binding="top_stage" cell="dim_stage.stage" id="head-top-stage" /> holds
            the most open pipeline</>}>
          Sales pipeline dashboard: open pipeline by stage and by region, with the win rate.
        </Masthead>

        <p className="tb-lede">
          <Value binding="top_stage" cell="dim_stage.stage" /> holds{" "}
          <Value binding="top_stage" cell="pipeline_value" format="currency0" /> of the{" "}
          <Value binding="kpis" cell="pipeline_value" format="currency0" /> still open, with a
          win rate of <Value binding="kpis" cell="win_rate" format="percent" />.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="pipeline_value" format="currency0" label="Open pipeline"
               context="sum of open-stage amounts" id="kpi-pipeline" />
          <Kpi binding="kpis" cell="win_rate" format="percent" label="Win rate"
               context="won deals / closed deals" id="kpi-win" />
          <Kpi binding="kpis" cell="won_value" format="currency0" label="Won value"
               context="amount on won deals" id="kpi-won" />
        </div>

        <div className="tb-grid">
          <section className="tb-card tb-span-8">
            <h2>Open pipeline by stage</h2>
            <p className="tb-note">Stages with open deals, largest first.</p>
            <Chart binding="by_stage" type="barh" x="dim_stage.stage" y="pipeline_value"
                   valueFormat="currency_compact" id="chart-by-stage" />
          </section>
          <section className="tb-card tb-span-4">
            <h2>Pipeline by region</h2>
            <p className="tb-note">The filter chooses rows; it never computes a number.</p>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Filter binding="by_region" column="dim_region.region" label="Region" />
              <Download binding="by_region" />
            </div>
            <Table binding="by_region" id="tbl-region" sort bars="pipeline_value"
                   columns={["dim_region.region", "pipeline_value", "win_rate", "won_value"]}
                   labels={{ "dim_region.region": "Region", pipeline_value: "Open pipeline" }}
                   formats={{ pipeline_value: "currency0", won_value: "currency0",
                              win_rate: "percent" }} />
          </section>
        </div>
        <Footer />
      </main>
    </div>
  );
}
