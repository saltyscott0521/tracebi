// Portfolio Desk: the book as an app people work in. Every number is a kit
// figure (<Kpi>, <Value>, <Chart>, <Table>) with literal binding and cell, so
// the build records it as a claim and the receipt names it. Controls choose
// which stamped rows show; they never compute a number.
import { LayoutDashboard, Table2, Landmark } from "lucide-react";
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Search, Download,
         useUrlState, usePrinting } from "tracebi";

const TITLE = "Portfolio Desk";
const VIEWS = { Overview: LayoutDashboard, Holdings: Table2, Funds: Landmark };

function Header({ view }) {
  return <h1 className="text-2xl font-semibold tracking-tight">{view}</h1>;
}

function Overview() {
  return (
    <>
      <p className="tb-lede">
        The book is worth <Value binding="totals" cell="fair_value" format="currency_compact" />,
        marked at <Value binding="totals" cell="mark" /> of cost.{" "}
        <Value binding="weakest_fund" cell="dim_fund.fund" /> carries the lowest mark,
        at <Value binding="weakest_fund" cell="mark" />.
      </p>
      <div className="tb-grid">
        <Kpi lead binding="totals" cell="fair_value" format="currency_compact"
             label="Fair value" context="three funds, administrator marks" id="kpi-fv" />
        <Kpi binding="totals" cell="unrealized" format="currency_compact"
             label="Unrealized" context="fair value less cost" id="kpi-unrealized" />
        <Kpi binding="totals" cell="positions" label="Positions" id="kpi-positions" />
        <Kpi binding="totals" cell="wtd_spread_bps" format="comma"
             label="Spread, bps" context="par-weighted" id="kpi-spread" />
      </div>
      <div className="tb-grid">
        <section className="tb-card tb-span-8">
          <h2>Fair value by sector</h2>
          <p className="tb-note">Largest first. Hover a bar for its value.</p>
          <Chart binding="by_sector" type="barh" x="dim_issuer.sector" y="fair_value"
                 valueFormat="currency_compact" />
        </section>
        <section className="tb-card tb-span-4">
          <h2>Watch list</h2>
          <p className="tb-note">The five lowest marks in the book.</p>
          <Table binding="watch" columns={["dim_issuer.issuer", "mark"]}
                 labels={{ "dim_issuer.issuer": "Issuer" }} />
        </section>
      </div>
    </>
  );
}

function Holdings() {
  return (
    <section className="tb-card">
      <h2>Every holding</h2>
      <p className="tb-note">One row per issuer and fund. Search and the filters choose
        rows; the CSV is the stamped data, verbatim.</p>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Search binding="holdings" placeholder="Find an issuer…" />
        <Filter column="dim_issuer.sector" label="Sector" />
        <Filter column="dim_fund.fund" label="Fund" />
        <Download binding="holdings" />
      </div>
      <Table binding="holdings" id="holdings-table" sort rows="all" bars="fair_value"
             columns={["dim_issuer.issuer", "dim_issuer.sector", "dim_fund.fund", "fair_value",
                       "unrealized", "mark", "wtd_spread_bps"]}
             labels={{ "dim_issuer.issuer": "Issuer", "dim_issuer.sector": "Sector",
                       "dim_fund.fund": "Fund", "wtd_spread_bps": "Spread, bps" }}
             formats={{ "wtd_spread_bps": "comma" }} />
    </section>
  );
}

function Funds() {
  return (
    <>
      <div className="tb-grid">
        <section className="tb-card tb-span-6">
          <h2>Fair value by fund</h2>
          <Chart binding="by_fund" type="bar" x="dim_fund.fund" y="fair_value"
                 valueFormat="currency_compact" />
        </section>
        <section className="tb-card tb-span-6">
          <h2>Unrealized by fund</h2>
          <p className="tb-note">Fair value less cost. Every fund is below what it paid.</p>
          <Chart binding="by_fund" type="bar" x="dim_fund.fund" y="unrealized"
                 valueFormat="currency_compact" id="chart-fund-unrealized" />
        </section>
      </div>
      <section className="tb-card">
        <h2>The three funds</h2>
        <Table binding="by_fund" id="funds-table" sort
               columns={["dim_fund.fund", "fair_value", "unrealized", "mark", "positions",
                         "wtd_spread_bps"]}
               labels={{ "dim_fund.fund": "Fund", "wtd_spread_bps": "Spread, bps" }}
               formats={{ "wtd_spread_bps": "comma" }} />
      </section>
    </>
  );
}

const PAGES = { Overview, Holdings, Funds };

export default function App() {
  // The view lives in the URL (#view=Holdings): a shared link opens on it.
  const [view, setView] = useUrlState("view", "Overview");
  const View = PAGES[view] || Overview;
  // Printed (Ctrl+P, or the PDF build), the page holds every view.
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink md:flex">
      <aside className="shrink-0 border-b border-rule bg-card p-3 md:sticky md:top-0
                        md:h-screen md:w-60 md:border-r md:border-b-0 print:hidden">
        {/* The masthead in the sidebar: the title, what it is, when it was built
            and the verdict chip. */}
        <Masthead title={TITLE} kicker="Direct lending" data-tb-title="nav"
          className="mb-3 border-b border-rule px-2.5 pb-3">
          Three funds, one book.
        </Masthead>
        <nav className="flex gap-1 md:flex-col">
          {Object.entries(VIEWS).map(([name, Icon]) => (
            <button key={name} onClick={() => setView(name)}
              aria-current={view === name ? "page" : undefined}
              className={"flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm " +
                (view === name ? "bg-surface font-medium text-ink"
                               : "text-muted hover:bg-surface hover:text-ink")}>
              <Icon size={16} />{name}
            </button>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 space-y-8 px-6 py-7">
        <Header view={printing ? TITLE : view} />
        {printing ? <><Overview /><Holdings /><Funds /></> : <View />}
        {/* The footer ends this column, not the page under the sidebar. */}
        <Footer />
      </main>
    </div>
  );
}
