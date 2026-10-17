// SaaS MRR Dashboard: an app (the React lane). Every number is a kit figure
// (<Kpi>, <Value>, <Chart>, <Spark>, <Table>) with a literal binding and cell,
// so the build records it and the receipt names it. The plan filter chooses
// rows; it never computes a number.
import { Masthead, Footer, Kpi, Value, Spark, Chart, Table, Filter, Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead kicker="SaaS metrics"
          title={<><Value binding="top_plan" cell="dim_plan.plan" id="head-top-plan" /> leads
            ending MRR</>}>
          SaaS MRR dashboard: recurring revenue, customers and churn, month by month.
        </Masthead>

        <p className="tb-lede">
          <Value binding="top_plan" cell="dim_plan.plan" /> holds{" "}
          <Value binding="top_plan" cell="ending_mrr" format="currency0" /> of the{" "}
          <Value binding="kpis" cell="ending_mrr" format="currency0" id="val-mrr-inline" /> book,
          across <Value binding="kpis" cell="customers" format="comma" id="val-customers-inline" /> customers,
          with logo churn of <Value binding="kpis" cell="logo_churn" format="percent" id="val-churn-inline" />.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="ending_mrr" format="currency0" label="Ending MRR"
               context="latest month in the warehouse" id="kpi-mrr">
            <Spark binding="by_month" x="dim_month.month" y="ending_mrr" valueFormat="currency0" />
          </Kpi>
          <Kpi binding="kpis" cell="customers" format="comma" label="Customers"
               context="logos active that month" id="kpi-customers">
            <Spark binding="by_month" type="line" x="dim_month.month" y="customers"
                   valueFormat="comma" />
          </Kpi>
          <Kpi binding="kpis" cell="logo_churn" format="percent" label="Logo churn"
               context="lost / starting logos, that month" id="kpi-churn" />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <section className="tb-card lg:col-span-2">
            <h2>Ending MRR by month</h2>
            <p className="tb-note">Period-end balance each month; the last point is today's book.</p>
            <Chart binding="by_month" type="area" x="dim_month.month" y="ending_mrr"
                   valueFormat="currency0" mark="last" id="chart-by-month" />
          </section>
          <section className="tb-card">
            <h2>Ending MRR by plan</h2>
            <p className="tb-note">The filter chooses rows; it never computes a number.</p>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Filter binding="by_plan" column="dim_plan.plan" label="Plan" />
              <Download binding="by_plan" />
            </div>
            <Table binding="by_plan" id="tbl-plan" sort bars="ending_mrr"
                   columns={["dim_plan.plan", "ending_mrr", "customers", "logo_churn"]}
                   labels={{ "dim_plan.plan": "Plan", ending_mrr: "Ending MRR" }}
                   formats={{ ending_mrr: "currency0", customers: "comma", logo_churn: "percent" }} />
          </section>
        </div>
        <Footer />
      </main>
    </div>
  );
}
