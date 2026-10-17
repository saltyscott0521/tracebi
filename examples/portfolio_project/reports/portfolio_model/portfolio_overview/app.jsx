// Portfolio Overview: the book at a glance, an app with top tabs. Every number
// is a kit figure (<Kpi>, <Value>, <Chart>, <Table>) with a literal binding and
// cell, so the build records it and the receipt names it.
import { LayoutDashboard, Building2, Landmark } from "lucide-react";
import { Masthead, Footer, Kpi, Value, Chart, Table, Download, useUrlState,
         usePrinting } from "tracebi";

const VIEWS = { Overview: LayoutDashboard, Issuers: Building2, Funds: Landmark };

function Overview() {
  return (
    <>
      <div className="tb-grid">
        <Kpi lead binding="kpis" cell="fair_value" format="currency_compact" label="Fair value"
             context="administrator marks, three funds" id="fig-fv" />
        <Kpi binding="kpis" cell="positions" label="Positions" id="fig-pos" />
        <Kpi binding="kpis" cell="unrealized" format="currency_compact" label="Unrealized"
             context="fair value less cost" id="fig-unrealized" />
      </div>
      <div className="tb-grid">
        <section className="tb-card tb-span-8">
          <h2>Fair value by sector</h2>
          <p className="tb-note">Largest first.</p>
          <Chart binding="by_sector" type="barh" x="dim_issuer.sector" y="fair_value"
                 valueFormat="currency_compact" id="fig-chart" />
        </section>
        <section className="tb-card tb-span-4">
          <h2>By fund</h2>
          <p className="tb-note">Fair value and the mark each fund carries.</p>
          <Table binding="by_fund" bars="fair_value" id="fig-funds"
                 columns={["dim_fund.fund", "fair_value", "mark"]}
                 labels={{ "dim_fund.fund": "Fund" }}
                 formats={{ fair_value: "currency_compact" }} />
        </section>
      </div>
    </>
  );
}

function Issuers() {
  return (
    <section className="tb-card">
      <h2>Top issuers</h2>
      <p className="tb-note">The eight largest exposures. Mark is fair value over cost.</p>
      <div className="mb-3"><Download binding="top_issuers" /></div>
      <Table binding="top_issuers" sort bars="fair_value" id="fig-top"
             labels={{ "dim_issuer.issuer": "Issuer", cost_basis: "Cost" }} />
    </section>
  );
}

function Funds() {
  return (
    <section className="tb-card">
      <h2>Fair value by fund</h2>
      <Chart binding="by_fund" type="bar" x="dim_fund.fund" y="fair_value"
             valueFormat="currency_compact" id="fig-fund-chart" />
    </section>
  );
}

const PAGES = { Overview, Issuers, Funds };

export default function App() {
  // The view lives in the URL (#view=Issuers): a shared link opens on it.
  const [view, setView] = useUrlState("view", "Overview");
  const View = PAGES[view] || Overview;
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead kicker="Direct lending · Portfolio overview"
          title={<>The book is marked at <Value binding="kpis" cell="mark" id="head-mark" /> of
            cost</>}>
          Three funds, one Schedule of Investments. Every number is a query against the model.
        </Masthead>
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
        {printing ? <><Overview /><Issuers /><Funds /></> : <View />}
        <Footer />
      </main>
    </div>
  );
}
