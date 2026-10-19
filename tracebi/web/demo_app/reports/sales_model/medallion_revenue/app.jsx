// Medallion Revenue: Landing (raw ingest) → Manipulation (deduplication) →
// Final (star schema). This app queries the model that reads the silver
// tables; no pandas in the loop. Every number is a kit figure. The filters
// and the revenue range cut both views.
import { Layers, Truck } from "lucide-react";
import { Masthead, Footer, Kpi, Chart, Table, Filter, Range, SelectionBar, useUrlState,
         usePrinting } from "tracebi";

const VIEWS = { "All orders": Layers, "Shipped orders": Truck };

function AllOrders() {
  return (
    <>
      <div className="tb-grid">
        <Kpi lead binding="totals" cell="revenue" format="currency0" label="Revenue"
             context="the orders in view, as the pipeline kept them" id="kpi-revenue" />
        <Kpi binding="totals" cell="qty" format="comma" label="Units" id="kpi-units" />
        <Kpi binding="totals" cell="cost" format="currency0" label="Cost" id="kpi-cost" />
      </div>
      <div className="tb-grid">
        <section className="tb-card tb-span-8">
          <h2>Revenue by region</h2>
          <Chart binding="by_region" type="barh" x="dim_customer.region" y="revenue"
                 valueFormat="currency_compact" />
        </section>
        <section className="tb-card tb-span-4">
          <h2>Region summary</h2>
          <Table binding="by_region" columns={["dim_customer.region", "revenue", "qty"]}
                 labels={{ "dim_customer.region": "Region", qty: "Units" }}
                 formats={{ revenue: "currency0", qty: "comma" }} />
        </section>
      </div>
    </>
  );
}

function Shipped() {
  return (
    <>
      <div className="tb-grid">
        <Kpi lead binding="shipped" cell="revenue" format="currency0" label="Shipped revenue"
             context="orders with status shipped" id="kpi-shipped-revenue" />
        <Kpi binding="shipped" cell="order_id" format="comma" label="Shipped orders"
             id="kpi-shipped-orders" />
      </div>
      <div className="tb-grid">
        <section className="tb-card tb-span-6">
          <h2>Shipped revenue by segment</h2>
          <Chart binding="shipped_by_segment" type="bar" x="dim_customer.segment" y="revenue"
                 valueFormat="currency_compact" />
        </section>
        <section className="tb-card tb-span-6">
          <h2>Segment breakdown</h2>
          <Table binding="shipped_by_segment"
                 labels={{ "dim_customer.segment": "Segment", order_id: "Orders" }}
                 formats={{ revenue: "currency0", order_id: "comma" }} />
        </section>
      </div>
    </>
  );
}

const PAGES = { "All orders": AllOrders, "Shipped orders": Shipped };

export default function App() {
  // The view lives in the URL (#view=Shipped orders): a shared link opens on it.
  const [view, setView] = useUrlState("view", "All orders");
  const View = PAGES[view] || AllOrders;
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Masthead title="Medallion revenue">
          Landing → Manipulation → Final: revenue from the model that reads the cleaned
          silver tables.
        </Masthead>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <Filter column="dim_customer.region" label="Region" />
          <Filter column="dim_customer.segment" label="Segment" />
          <Range column="revenue" label="Order revenue" />
        </div>
        <SelectionBar />
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
        {printing ? <><AllOrders /><Shipped /></> : <View />}
        <Footer />
      </main>
    </div>
  );
}
