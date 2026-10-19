// Portfolio Concentration: how concentrated the book is by issuer, an app.
// Rank, share and cumulative share are governed window measures declared in
// the model; every number is a kit figure, so its trace names it. A window
// measure re-runs over what the page picks (a sector, a bar, a row), so under
// a selection a rank or a share is within it, and the copy says so.
import { Masthead, Footer, Kpi, Value, Chart, Table, Filter, Download,
         SelectionBar } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead
          title={<>The five largest issuers hold{" "}
            <Value binding="fifth" cell="fv_cum_share" id="head-top5" /> of the fair value in
            view</>}>
          Issuer concentration across the funds. Rank, share and cumulative share are
          window measures declared in the model; pick a sector and they are taken
          within it.
        </Masthead>

        {/* A page filter: every figure re-runs, ranks and shares included.
            The bar under it says what is picked. */}
        <div>
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            <Filter column="dim_issuer.sector" label="Sector" />
          </div>
          <SelectionBar />
        </div>

        <div className="tb-grid">
          {/* The fifth issuer's row, or the last when fewer than five are in
              view: its rank says which. */}
          <Kpi lead binding="fifth" cell="fv_cum_share" label="Top five issuers, share in view"
               id="kpi-top5">
            <span className="tb-kpi-context">cumulative fair value, through rank{" "}
              <Value binding="fifth" cell="fv_rank" id="val-top5-rank" /></span>
          </Kpi>
          <Kpi binding="largest" cell="fv_share" label="Largest issuer" id="kpi-largest-share">
            <span className="tb-kpi-context"><Value binding="largest" cell="dim_issuer.issuer"
              id="val-largest" /></span>
          </Kpi>
          <Kpi binding="largest_sector" cell="fv_share" label="Largest sector" id="kpi-sector-share">
            <span className="tb-kpi-context"><Value binding="largest_sector" cell="dim_issuer.sector"
              id="val-largest-sector" /></span>
          </Kpi>
        </div>

        <div className="tb-grid">
          <section className="tb-card tb-span-6">
            <h2>Share of fair value, by issuer</h2>
            <p className="tb-note">Each issuer's fair value over the total in view.
              Click a bar to select its issuer.</p>
            <Chart binding="concentration" type="barh" x="dim_issuer.issuer" y="fv_share"
                   valueFormat="percent" height={420} id="fig-share_chart" />
          </section>
          <section className="tb-card tb-span-6">
            <h2>Cumulative share, largest issuer first</h2>
            <p className="tb-note">The steeper the start, the more concentrated the
              holdings. Under a selection the curve starts again at its largest issuer.</p>
            <Chart binding="concentration" type="area" x="fv_rank" y="fv_cum_share"
                   valueFormat="percent" xTitle="Issuers, by rank" mark={["first", "last"]}
                   height={420} id="fig-curve_chart" />
          </section>
        </div>

        <section className="tb-card">
          <h2>Issuer ranking</h2>
          <p className="tb-note">Every issuer in view, largest first; rank and shares are
            within the selection. Click a row to select its issuer; again to clear.</p>
          <div className="mb-3"><Download binding="concentration" /></div>
          {/* The table narrows with its own picks (highlight off): it shows
              the sector column, and a highlighting table keeps every value of
              the columns it selects, so a sector picked above would leave its
              ranks taken over the whole book. */}
          <div data-tb-highlight="off">
            <Table binding="concentration" selectRows sort rows="all" bars="fv_share" id="fig-ranking"
                   columns={["fv_rank", "dim_issuer.issuer", "dim_issuer.sector", "fair_value",
                             "fv_share", "fv_cum_share"]}
                   labels={{ fv_rank: "Rank", "dim_issuer.issuer": "Issuer",
                             "dim_issuer.sector": "Sector", fv_share: "Share in view",
                             fv_cum_share: "Cumulative share" }}
                   formats={{ fair_value: "currency0", fv_share: "percent", fv_cum_share: "percent" }} />
          </div>
        </section>
        <Footer />
      </main>
    </div>
  );
}
