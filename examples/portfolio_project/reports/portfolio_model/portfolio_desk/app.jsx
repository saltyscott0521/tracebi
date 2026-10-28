// Portfolio Desk: the book as an app people work in. Every number is a kit
// figure (<Kpi>, <Value>, <Chart>, <Table>) with literal binding and cell, so
// the build records it as a claim and its trace names it. Search narrows the
// rows shown; the filters recompute every view, each figure by its own query,
// and so does every other gesture: a click on a bar or a watch-list row, the
// spread range. The filters and the range live in the sidebar, so what they
// pick holds on every view. The selection bar says what is picked.
// The Funds view's two <EChart>s are charts the kit's <Chart> cannot draw: a
// treemap of a binding's columns as they are (a claim, like any kit figure)
// and a sankey whose links the page computes from a binding's rows (not a
// claim, and it says so). Both are live: they redraw under the selection.
import { useState, useEffect } from "react";
import { LayoutDashboard, Table2, Landmark } from "lucide-react";
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Search, Download, Range,
         SelectionBar, EChart, useBinding, useUrlState, usePrinting, chartTokens } from "tracebi";

const TITLE = "Portfolio Desk";
const VIEWS = { Overview: LayoutDashboard, Holdings: Table2, Funds: Landmark };

function Header({ view }) {
  return <h1 className="text-2xl font-semibold tracking-tight">{view}</h1>;
}

// How many funds are in view, from the funds_in_view figure's own query
// result; null as built, when the authored sentence stands. "The lowest of
// any fund" needs more than one fund to compare.
function useFundsInView() {
  const [funds, setFunds] = useState(null);
  useEffect(() => {
    const tb = window.tracebi;
    if (!tb || !tb.onSelection) return undefined;
    const read = () => {
      const res = tb.result("val-funds-in-view");
      setFunds(!res ? null
        : res.rows.length ? Number(res.rows[0][res.cols.indexOf("funds")]) || 0 : 0);
    };
    read();
    return tb.onSelection(read);
  }, []);
  return funds;
}

function Overview() {
  const funds = useFundsInView();
  return (
    <>
      <p className="tb-lede">
        The holdings in view are worth{" "}
        <Value binding="totals" cell="fair_value" format="currency_compact" />, marked
        at <Value binding="totals" cell="mark" /> of cost.{" "}
        <span hidden={funds !== null && funds < 2}>
          <Value binding="weakest_fund" cell="dim_fund.fund" /> carries the lowest mark of
          the <Value binding="funds_in_view" cell="funds" id="val-funds-in-view" /> funds
          in view, at <Value binding="weakest_fund" cell="mark" />.</span>
        <span hidden={funds !== 1}>
          <Value binding="weakest_fund" cell="dim_fund.fund" id="val-only-fund" /> is the
          only fund in view.</span>
      </p>
      <div className="tb-grid">
        <Kpi lead binding="totals" cell="fair_value" format="currency_compact"
             label="Fair value" context="administrator marks" id="kpi-fv" />
        <Kpi binding="totals" cell="unrealized" format="currency_compact"
             label="Unrealized" context="fair value less cost" id="kpi-unrealized" />
        <Kpi binding="totals" cell="positions" label="Positions" id="kpi-positions" />
        <Kpi binding="totals" cell="wtd_spread_bps" format="comma"
             label="Spread, bps" context="par-weighted" id="kpi-spread" />
      </div>
      <div className="tb-grid">
        <section className="tb-card tb-span-8">
          <h2>Fair value by sector</h2>
          <p className="tb-note">Largest first. Click a bar to select its sector;
            shift-click adds one.</p>
          <Chart binding="by_sector" type="barh" x="dim_issuer.sector" y="fair_value"
                 valueFormat="currency_compact" />
        </section>
        <section className="tb-card tb-span-4">
          <h2>Watch list</h2>
          <p className="tb-note">The five lowest marks in view. Click an issuer
            to select it.</p>
          <Table binding="watch" selectRows columns={["dim_issuer.issuer", "mark"]}
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
      <p className="tb-note">One row per issuer and fund in view. Search chooses rows;
        the sidebar's filters (pick several funds) recompute every view. The CSV is
        the stamped data, verbatim.</p>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Search binding="holdings" placeholder="Find an issuer…" />
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
          <p className="tb-note">Click a bar to select its fund.</p>
          <Chart binding="by_fund" type="bar" x="dim_fund.fund" y="fair_value"
                 valueFormat="currency_compact" />
        </section>
        <section className="tb-card tb-span-6">
          <h2>Unrealized by fund</h2>
          <p className="tb-note">Fair value less cost. A bar below zero is a fund whose
            holdings in view are marked below what it paid.</p>
          <Chart binding="by_fund" type="bar" x="dim_fund.fund" y="unrealized"
                 valueFormat="currency_compact" id="chart-fund-unrealized" />
        </section>
      </div>
      <div className="tb-grid">
        <section className="tb-card tb-span-6">
          <h2>Fair value by sector</h2>
          <p className="tb-note">Each sector's share of the book. Click one to select it.</p>
          {/* binding, x and y literal: the chart plots the binding's columns as
              they are, so the build records it as a claim and checks them. */}
          <EChart binding="by_sector" type="treemap" x="dim_issuer.sector" y="fair_value"
                  format="currency_compact" id="ech-sector-treemap" height={300}
                  ariaLabel="Fair value by sector, as a treemap" />
        </section>
        <section className="tb-card tb-span-6">
          <h2>Where each fund's money sits</h2>
          <p className="tb-note">Fund to sector, by fair value. Drawn by this page from
            the fund-by-sector rows: live, not a checked figure.</p>
          <FundSectorFlow />
        </section>
      </div>
      <section className="tb-card">
        <h2>The funds side by side</h2>
        <Table binding="by_fund" id="funds-table" sort
               columns={["dim_fund.fund", "fair_value", "unrealized", "mark", "positions",
                         "wtd_spread_bps"]}
               labels={{ "dim_fund.fund": "Fund", "wtd_spread_bps": "Spread, bps" }}
               formats={{ "wtd_spread_bps": "comma" }} />
      </section>
    </>
  );
}

// A chart of the page's own: the links are computed here from the rows of
// fund_sector (re-run under the selection), so it carries data-tb-computed
// and is presentation, not a claim. Its colours follow the chart engine's
// rule: a category takes the palette slot of its first appearance in the
// binding's stamped (unfiltered) rows, so each sector here wears the colour
// the treemap gives it whatever the selection leaves, and the funds take the
// slots after the sectors.
function stampedOrder(binding, column) {
  const tb = window.tracebi;
  return [...new Set((tb ? tb.data(binding) : []).map((r) => String(r[column])))];
}

function FundSectorFlow() {
  const rows = useBinding("fund_sector");
  const funds = [...new Set(rows.map((r) => r["dim_fund.fund"]))];
  const sectors = [...new Set(rows.map((r) => r["dim_issuer.sector"]))];
  const palette = chartTokens().palette || [];
  const sectorOrder = stampedOrder("by_sector", "dim_issuer.sector");
  const fundOrder = stampedOrder("fund_sector", "dim_fund.fund");
  const colour = (slot) => (palette.length ? palette[Math.max(slot, 0) % palette.length] : undefined);
  const node = (name, slot) => ({ name, itemStyle: { color: colour(slot) } });
  return (
    <EChart height={300} id="ech-fund-sector" ariaLabel="Fair value from each fund to each sector"
      option={{
        tooltip: { trigger: "item" },
        series: [{
          type: "sankey", left: 8, right: 110, nodeGap: 10, emphasis: { focus: "adjacency" },
          lineStyle: { color: "gradient", opacity: 0.35 },
          data: [...funds.map((f) => node(f, sectorOrder.length + fundOrder.indexOf(String(f)))),
                 ...sectors.map((s) => node(s, sectorOrder.indexOf(String(s))))],
          links: rows.map((r) => ({ source: r["dim_fund.fund"], target: r["dim_issuer.sector"],
                                    value: Number(r.fair_value) })),
        }],
      }} />
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
      {/* The column runs the page's whole height (its ground never stops
          short of a long view); its contents stay in sight as the view
          scrolls. */}
      <aside className="shrink-0 border-b border-rule bg-card p-3 md:min-h-screen md:w-60
                        md:border-r md:border-b-0 print:hidden">
        <div className="md:sticky md:top-3 md:max-h-screen md:overflow-y-auto">
          {/* The masthead in the sidebar: the title, what it is, when it was built
              and the verdict chip. */}
          <Masthead title={TITLE} data-tb-title="nav"
            className="mb-3 border-b border-rule px-2.5 pb-3">
            The funds' holdings, one desk.
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
          {/* Page filters and a range over each holding's own spread: in the
              sidebar, so they stay put while the views change. */}
          <div className="mt-3 flex flex-wrap items-start gap-2 border-t border-rule
                          px-2.5 pt-3 md:flex-col">
            <Filter column="dim_issuer.sector" label="Sector" />
            <Filter column="dim_fund.fund" label="Fund" multiple />
            <Range column="spread_bps" label="Spread, bps" />
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 space-y-8 px-6 py-7">
        <Header view={printing ? TITLE : view} />
        {/* What the reader picked, one chip per value; hidden as built. */}
        <SelectionBar />
        {printing ? <><Overview /><Holdings /><Funds /></> : <View />}
        {/* The footer ends this column, not the page under the sidebar. */}
        <Footer />
      </main>
    </div>
  );
}
