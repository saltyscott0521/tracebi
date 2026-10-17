// Sales Rep Scorecard: an app (the React lane) with two views, by rep and by
// region. Every number is a kit figure, so the receipt names it. Win rate is
// won deals over closed deals inside the rep or region, a ratio of totals, not a
// mean of per-rep rates.
import { Users, Map } from "lucide-react";
import { Kpi, Value, Chart, Table, Filter, Download, Built,
         useUrlState, usePrinting } from "tracebi";

const VIEWS = { Reps: Users, Regions: Map };

function Reps() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="tb-card">
        <h2>Win rate by rep</h2>
        <Chart binding="by_rep" type="barh" x="dim_rep.rep" y="win_rate"
               valueFormat="percent" id="chart-win-by-rep" />
      </section>
      <section className="tb-card lg:col-span-2">
        <h2>Rep scorecard</h2>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Filter binding="by_rep" column="dim_rep.rep" label="Rep" />
          <Download binding="by_rep" />
        </div>
        <Table binding="by_rep" id="tbl-rep" sort bars="pipeline_value"
               columns={["dim_rep.rep", "pipeline_value", "won_value", "win_rate", "closed_deals"]}
               labels={{ "dim_rep.rep": "Rep", pipeline_value: "Open pipeline" }}
               formats={{ pipeline_value: "currency0", won_value: "currency0",
                          win_rate: "percent", closed_deals: "comma" }} />
      </section>
    </div>
  );
}

function Regions() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="tb-card">
        <h2>Open pipeline by region</h2>
        <Chart binding="by_region" type="barh" x="dim_region.region" y="pipeline_value"
               valueFormat="currency_compact" id="chart-pipeline-by-region" />
      </section>
      <section className="tb-card lg:col-span-2">
        <h2>Region scorecard</h2>
        <div className="mb-3"><Download binding="by_region" /></div>
        <Table binding="by_region" id="tbl-region" sort bars="pipeline_value"
               columns={["dim_region.region", "pipeline_value", "won_value", "win_rate",
                         "closed_deals"]}
               labels={{ "dim_region.region": "Region", pipeline_value: "Open pipeline" }}
               formats={{ pipeline_value: "currency0", won_value: "currency0",
                          win_rate: "percent", closed_deals: "comma" }} />
      </section>
    </div>
  );
}

const PAGES = { Reps, Regions };

export default function App() {
  // The view lives in the URL (#view=Regions): a shared link opens on it.
  const [view, setView] = useUrlState("view", "Reps");
  const View = PAGES[view] || Reps;
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="mx-auto max-w-6xl space-y-5 px-6 py-8">
        <header className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              <Value binding="top_rep" cell="dim_rep.rep" id="head-top-rep" /> leads win rate
            </h1>
            <p className="text-sm text-muted">Rep scorecard: win rate, open pipeline and won value,
              by rep and by region.</p>
          </div>
          <Built className="text-xs text-muted" />
        </header>

        <p className="tb-lede">
          <Value binding="top_rep" cell="dim_rep.rep" /> leads at{" "}
          <Value binding="top_rep" cell="win_rate" format="percent" />, on{" "}
          <Value binding="top_rep" cell="won_value" format="currency0" /> won. Open pipeline
          across the team is <Value binding="kpis" cell="pipeline_value" format="currency0" />.
        </p>

        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="win_rate" format="percent" label="Win rate"
               context="won deals / closed deals, the team" id="kpi-win" />
          <Kpi binding="kpis" cell="pipeline_value" format="currency0" label="Open pipeline"
               context="sum of open-stage amounts" id="kpi-pipeline" />
          <Kpi binding="kpis" cell="won_value" format="currency0" label="Won value"
               context="amount on won deals" id="kpi-won" />
        </div>

        <nav className="flex gap-1 border-b border-rule print:hidden">
          {Object.entries(VIEWS).map(([name, Icon]) => (
            <button key={name} onClick={() => setView(name)}
              aria-current={view === name ? "page" : undefined}
              className={"flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm " +
                (view === name ? "border-accent font-medium text-ink"
                               : "border-transparent text-muted hover:text-ink")}>
              <Icon size={15} />{name}
            </button>
          ))}
        </nav>
        {printing ? <><Reps /><Regions /></> : <View />}
      </main>
    </div>
  );
}
