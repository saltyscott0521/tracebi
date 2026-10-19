// SaaS MRR Dashboard: an app (the React lane). Every number is a kit figure
// (<Kpi>, <Value>, <Chart>, <Spark>, <Table>) with a literal binding and cell,
// so the build records it and its trace names it. The plan filter and the
// month range cut the whole page, and so does a click on a plan's row or a
// chart's month: every figure reruns its own query for what is picked. The
// balances are period-end, so a range ending earlier reads that month's book.
import { Masthead, Footer, Kpi, Value, Spark, Chart, Table, Filter, Range, SelectionBar,
         Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead
          title={<><Value binding="top_plan" cell="dim_plan.plan" id="head-top-plan" /> leads
            ending MRR</>}>
          SaaS MRR dashboard: recurring revenue, customers and churn, month by month.
        </Masthead>

        {/* The page's controls, then what is picked: one chip per value. */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <Filter column="dim_plan.plan" label="Plan" />
          <Range column="dim_month.month" label="Months" />
        </div>
        <SelectionBar />

        <p className="tb-lede">
          <Value binding="top_plan" cell="dim_plan.plan" /> holds{" "}
          <Value binding="top_plan" cell="ending_mrr" format="currency0" /> of the{" "}
          <Value binding="kpis" cell="ending_mrr" format="currency0" id="val-mrr-inline" /> book,
          across <Value binding="kpis" cell="customers" format="comma" id="val-customers-inline" /> customers,
          with logo churn of <Value binding="kpis" cell="logo_churn" format="percent" id="val-churn-inline" />.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="ending_mrr" format="currency0" label="Ending MRR"
               context="the latest month in view" id="kpi-mrr">
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

        <div className="tb-grid">
          <section className="tb-card tb-span-6">
            <h2>Ending MRR by month</h2>
            <p className="tb-note">Period-end balance each month; the last point is the latest
              month in view. Click a month to select it.</p>
            <Chart binding="by_month" type="area" x="dim_month.month" y="ending_mrr"
                   valueFormat="currency0" mark="last" id="chart-by-month" />
          </section>
          <section className="tb-card tb-span-6">
            <h2>Ending MRR by plan</h2>
            <p className="tb-note">Click a plan to select it; every figure on the page
              recomputes for it.</p>
            <div className="mb-3"><Download binding="by_plan" /></div>
            <Table binding="by_plan" id="tbl-plan" sort selectRows bars="ending_mrr"
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
