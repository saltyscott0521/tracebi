// Portfolio Concentration: how concentrated the book is by issuer, an app.
// Rank, share and cumulative share are governed window measures declared in
// the model; every number is a kit figure, so the receipt names it.
import { Masthead, Footer, Kpi, Value, Chart, Table, Download } from "tracebi";

export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead
          title={<>The five largest issuers hold{" "}
            <Value binding="fifth" cell="fv_cum_share" id="head-top5" /> of the book</>}>
          Issuer concentration across the three funds. Rank, share and cumulative share are
          window measures declared in the model.
        </Masthead>

        <div className="tb-grid">
          <Kpi lead binding="fifth" cell="fv_cum_share" label="Top five issuers, share of book"
               context="cumulative fair value, largest first" id="kpi-top5" />
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
            <h2>Share of the book, by issuer</h2>
            <p className="tb-note">Each issuer's fair value over the total.</p>
            <Chart binding="concentration" type="barh" x="dim_issuer.issuer" y="fv_share"
                   valueFormat="percent" height={420} id="fig-share_chart" />
          </section>
          <section className="tb-card tb-span-6">
            <h2>Cumulative share, largest issuer first</h2>
            <p className="tb-note">The steeper the start, the more concentrated the book.</p>
            <Chart binding="concentration" type="area" x="fv_rank" y="fv_cum_share"
                   valueFormat="percent" xTitle="Issuers, by rank" mark={["first", "last"]}
                   height={420} id="fig-curve_chart" />
          </section>
        </div>

        <section className="tb-card">
          <h2>Issuer ranking</h2>
          <p className="tb-note">Every issuer, largest first. Sort by any column.</p>
          <div className="mb-3"><Download binding="concentration" /></div>
          <Table binding="concentration" sort rows="all" bars="fv_share" id="fig-ranking"
                 columns={["fv_rank", "dim_issuer.issuer", "dim_issuer.sector", "fair_value",
                           "fv_share", "fv_cum_share"]}
                 labels={{ fv_rank: "Rank", "dim_issuer.issuer": "Issuer",
                           "dim_issuer.sector": "Sector", fv_share: "Share of book",
                           fv_cum_share: "Cumulative share" }}
                 formats={{ fair_value: "currency0", fv_share: "percent", fv_cum_share: "percent" }} />
        </section>
        <Footer />
      </main>
    </div>
  );
}
