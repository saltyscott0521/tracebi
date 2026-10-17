"""The React-lane starter that ``tracebi new-report`` writes for a dashboard.

A string template, not a component library: the scaffold is the teaching page
for app.jsx, as ``_report_template_html`` is for template.html — the kit, a
KPI strip with a lead, a wide panel beside a narrow one, controls, and the
look the builder chose (navigation and title placement).
"""

from __future__ import annotations

from tracebi.reports.derive import in_sentence

_APP_HEAD = '''// app.jsx — this report's page, a React app (the React lane).
// Numbers shown through the tracebi kit (<Kpi>, <Value>, <Chart>, <Table>)
// carry the receipt: the build reads their binding / cell / x / y as claims,
// so keep those literal strings. A number your own code computes or draws is
// the app's presentation, not a checked figure. Imports: react, recharts,
// lucide-react (icons by name), tracebi. Colours: bg-page bg-card bg-surface
// text-ink text-muted border-rule bg-accent follow the page's theme and mode.
// The kit and patterns: docs/reference/app-jsx.md.
import { LayoutDashboard, Table2 } from "lucide-react";
import { Kpi, Value, Spark, Chart, Table, Filter, Search, Download, Built, Segmented,
         useUrlState } from "tracebi";

const TITLE = "__TITLE__";
const VIEWS = { Overview: LayoutDashboard, Detail: Table2 };
'''

_APP_HEADERS = {
    "left": '''
function Header() {
  return (
    <header className="flex flex-wrap items-end justify-between gap-2">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{TITLE}</h1>
        <p className="text-sm text-muted">One line on what this page is for.</p>
      </div>
      <Built className="text-xs text-muted" />
    </header>
  );
}
''',
    "center": '''
function Header() {
  return (
    <header className="text-center">
      <h1 className="text-2xl font-semibold tracking-tight">{TITLE}</h1>
      <p className="text-sm text-muted">One line on what this page is for.</p>
      <Built className="text-xs text-muted" />
    </header>
  );
}
''',
    "banner": '''
function Header() {
  return (
    <header className="rounded-panel bg-accent px-8 py-7 text-on-accent">
      <h1 className="text-2xl font-semibold tracking-tight">{TITLE}</h1>
      <p className="text-sm opacity-85">One line on what this page is for.</p>
      <Built className="text-xs opacity-75" />
    </header>
  );
}
''',
}

_APP_VIEWS_DIM = '''
// Lead with the answer: one sentence, its numbers bound to the stamped rows.
function Overview() {
  return (
    <>
      <p className="tb-lede">
        <Value binding="top" cell="__DIM__" /> leads on __MLOWER__ with{" "}
        <Value binding="top" cell="__MEASURE__" />. Rewrite this sentence as the
        page's finding.
      </p>
      {/* One KPI strip: the lead number twice as wide, then what explains it. */}
      <div className="tb-grid">
        <Kpi lead binding="totals" cell="__MEASURE__" label="__MLABEL__"
             context="state the period and comparison" />
        <Kpi binding="top" cell="__DIM__" label="Top __DLOWER__" id="kpi-top" />
        <Kpi binding="top" cell="__MEASURE__" label="__MLABEL__, top __DLOWER__"
             id="kpi-top-__MEASURE_ID__" />
      </div>
      {/* A wide panel beside a narrow one: the breakdown and its ranking. */}
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="tb-card lg:col-span-2">
          <h2>__MLABEL__ by __DLABEL__</h2>
          <p className="tb-note">Largest first.</p>
          <Chart binding="breakdown" type="bar" x="__DIM__" y="__MEASURE__"
                 valueFormat="compact" />
        </section>
        <section className="tb-card">
          <h2>Ranking</h2>
          <Table binding="breakdown" sort bars="__MEASURE__" />
        </section>
      </div>
    </>
  );
}

// Controls choose which stamped rows show; they never compute a number.
function Detail() {
  return (
    <section className="tb-card">
      <h2>Detail</h2>
      <p className="tb-note">Search and filter choose rows; the CSV is the stamped data, verbatim.</p>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Search binding="breakdown" />
        <Filter binding="breakdown" column="__DIM__" label="__DLABEL__" />
        <Download binding="breakdown" />
      </div>
      <Table binding="breakdown" id="detail-table" sort />
    </section>
  );
}
'''

_APP_VIEWS_TOTALS = '''
function Overview() {
  return (
    <div className="tb-grid">
      <Kpi lead binding="totals" cell="__MEASURE__" label="__MLABEL__"
           context="state the period and comparison" />
    </div>
  );
}

function Detail() {
  return (
    <section className="tb-card">
      <h2>Detail</h2>
      <Table binding="totals" />
    </section>
  );
}
'''

_APP_VIEWS_TREND = '''
// A trend: the latest period leads, its shape beside it, the series below.
function Overview() {
  const [show, setShow] = useUrlState("show", "Chart");
  return (
    <>
      <div className="tb-grid">
        <Kpi lead binding="latest" cell="__MEASURE__" label="__MLABEL__, latest __DLOWER__"
             context="state the comparison that makes it mean something">
          <Spark binding="by_period" x="__DIM__" y="__MEASURE__" valueFormat="compact" />
        </Kpi>
        <Kpi binding="latest" cell="__DIM__" label="Latest __DLOWER__" id="kpi-latest-period" />
        <Kpi binding="totals" cell="__MEASURE__" label="__MLABEL__, all __DLOWER__s" />
      </div>
      <section className="tb-card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[0.95em] font-semibold">__MLABEL__ by __DLOWER__</h2>
          <Segmented label="Show" options={["Chart", "Table"]} value={show} onChange={setShow} />
        </div>
        {show === "Chart"
          ? <Chart binding="by_period" type="area" x="__DIM__" y="__MEASURE__" valueFormat="compact" />
          : <Table binding="by_period" id="trend-table" sort />}
      </section>
    </>
  );
}

function Detail() {
  return (
    <section className="tb-card">
      <h2>Every __DLOWER__</h2>
      <p className="tb-note">The stamped series; the CSV is the same rows, verbatim.</p>
      <div className="mb-4"><Download binding="by_period" /></div>
      <Table binding="by_period" id="detail-table" sort rows="all" />
    </section>
  );
}
'''

_APP_VIEWS_LEADERBOARD = '''
// A leaderboard: who leads, the top ten, then everyone.
function Overview() {
  return (
    <>
      <p className="tb-lede">
        <Value binding="top" cell="__DIM__" /> leads on __MLOWER__ with{" "}
        <Value binding="top" cell="__MEASURE__" />. Rewrite this sentence as the
        page's finding.
      </p>
      <div className="tb-grid">
        <Kpi lead binding="top" cell="__DIM__" label="Leading __DLOWER__" id="kpi-top"
             context="state what leading means here" />
        <Kpi binding="top" cell="__MEASURE__" label="__MLABEL__, leader" id="kpi-top-__MEASURE_ID__" />
        <Kpi binding="totals" cell="__MEASURE__" label="__MLABEL__, everyone" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="tb-card">
          <h2>Top ten</h2>
          <Chart binding="top10" type="barh" x="__DIM__" y="__MEASURE__" valueFormat="compact" />
        </section>
        <section className="tb-card">
          <h2>Full ranking</h2>
          <div className="mb-3"><Search binding="ranking" placeholder="Find a __DLOWER__…" /></div>
          <Table binding="ranking" sort bars="__MEASURE__" />
        </section>
      </div>
    </>
  );
}

function Detail() {
  return (
    <section className="tb-card">
      <h2>Every __DLOWER__</h2>
      <p className="tb-note">Search chooses rows; the CSV is the stamped data, verbatim.</p>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Search binding="ranking" />
        <Download binding="ranking" />
      </div>
      <Table binding="ranking" id="detail-table" sort rows="all" />
    </section>
  );
}
'''

_APP_SHELLS = {
    "": '''
export default function App() {
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Header />
        <Overview />
        <Detail />
      </main>
    </div>
  );
}
''',
    "top": '''
export default function App() {
  // The view lives in the URL (#view=Detail): a shared link opens on it.
  const [view, setView] = useUrlState("view", "Overview");
  const View = view === "Overview" ? Overview : Detail;
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Header />
        <nav className="flex gap-1 border-b border-rule">
          {Object.entries(VIEWS).map(([name, Icon]) => (
            <button key={name} onClick={() => setView(name)}
              className={"flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm " +
                (view === name ? "border-accent font-medium text-ink"
                               : "border-transparent text-muted hover:text-ink")}>
              <Icon size={15} />{name}
            </button>
          ))}
        </nav>
        <View />
      </main>
    </div>
  );
}
''',
    "side": '''
export default function App() {
  // The view lives in the URL (#view=Detail): a shared link opens on it.
  const [view, setView] = useUrlState("view", "Overview");
  const View = view === "Overview" ? Overview : Detail;
  return (
    <div className="min-h-screen bg-page text-ink md:flex">
      <aside className="shrink-0 border-b border-rule bg-card p-3 md:sticky md:top-0
                        md:h-screen md:w-60 md:border-r md:border-b-0">
__BRAND__
        <nav className="flex gap-1 md:flex-col">
          {Object.entries(VIEWS).map(([name, Icon]) => (
            <button key={name} onClick={() => setView(name)}
              className={"flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm " +
                (view === name ? "bg-surface font-medium text-ink"
                               : "text-muted hover:bg-surface hover:text-ink")}>
              <Icon size={16} />{name}
            </button>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 space-y-6 px-6 py-8">
__MAIN_HEADER__
        <View />
      </main>
    </div>
  );
}
''',
}

_BRAND_PLAIN = '''        <div className="mb-3 border-b border-rule px-2.5 pb-3 font-semibold">{TITLE}</div>'''
_BRAND_TITLE = '''        <div className="mb-3 border-b border-rule px-2.5 pb-3">
          <div className="font-semibold">{TITLE}</div>
          <p className="text-xs text-muted">One line on what this page is for.</p>
          <Built className="text-xs text-muted" />
        </div>'''


def _scorecard_views(measures, dim_ref, time_ref, humanise):
    """Every measure as a KPI (the first leads), each with its trend when the
    model has a time dimension; then all of them by the category."""
    kpis = []
    for i, m in enumerate(measures):
        lead = " lead" if i == 0 else ""
        spark = (f'\n          <Spark binding="by_period" x="{time_ref}" y="{m}" '
                 f'valueFormat="compact" />\n        ' if time_ref else "")
        close = f">{spark}</Kpi>" if time_ref else " />"
        kpis.append(f'        <Kpi{lead} binding="totals" cell="{m}" label="{humanise(m)}"{close}')
    cat = humanise(dim_ref) if dim_ref else ""
    by_cat = (f'''
      <section className="tb-card">
        <h2>By {in_sentence(cat)}</h2>
        <p className="tb-note">Every measure on the scorecard, for each {in_sentence(cat)}.</p>
        <Table binding="breakdown" sort />
      </section>''' if dim_ref else "")
    detail = (f'''
function Detail() {{
  return (
    <section className="tb-card">
      <h2>Every {in_sentence(cat)}</h2>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Filter binding="breakdown" column="{dim_ref}" label="{cat}" />
        <Download binding="breakdown" />
      </div>
      <Table binding="breakdown" id="detail-table" sort rows="all" />
    </section>
  );
}}
''' if dim_ref else '''
function Detail() {
  return (
    <section className="tb-card">
      <h2>Detail</h2>
      <Table binding="totals" />
    </section>
  );
}
''')
    return ('''
// A scorecard: every measure at a glance, each with its trend.
function Overview() {
  return (
    <>
      <div className="tb-grid">
''' + "\n".join(kpis) + '''
      </div>''' + by_cat + '''
    </>
  );
}
''' + detail)


def report_app_jsx(title, measure, dim_ref, *, nav="", title_at="left",
                   humanise=lambda s: s, job="overview", measures=None, time_ref=None):
    """The React-lane starter: one app.jsx over the scaffold's bindings,
    shaped by the job (overview: totals/top/breakdown; trend: totals/latest/
    by_period, with dim_ref the period; leaderboard: totals/top/ranking/top10)
    and the look the builder chose."""
    in_nav = nav == "side" and title_at == "nav"
    header = _APP_HEADERS.get(title_at if title_at in _APP_HEADERS else "left")
    if in_nav:
        header = '''
function Header({ view }) {
  return <h1 className="text-2xl font-semibold tracking-tight">{view}</h1>;
}
'''
    shell = _APP_SHELLS[nav if nav in _APP_SHELLS else ""]
    shell = shell.replace("__BRAND__", _BRAND_TITLE if in_nav else _BRAND_PLAIN)
    shell = shell.replace("__MAIN_HEADER__",
                          "        <Header view={view} />" if in_nav else "        <Header />")
    if job == "scorecard":
        views = _scorecard_views(measures or [measure], dim_ref, time_ref, humanise)
    else:
        views = (_APP_VIEWS_TOTALS if not dim_ref else
                 {"trend": _APP_VIEWS_TREND, "leaderboard": _APP_VIEWS_LEADERBOARD}.get(
                     job, _APP_VIEWS_DIM))
    head = _APP_HEAD
    if not nav:
        head = head.replace('import { LayoutDashboard, Table2 } from "lucide-react";\n', "")
        head = head.replace("const VIEWS = { Overview: LayoutDashboard, Detail: Table2 };\n", "")
    m_label = humanise(measure)
    d_label = humanise(dim_ref) if dim_ref else ""
    text = head + header + views + shell
    js = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
    for token, value in (("__TITLE__", js(title)), ("__MEASURE_ID__", measure.replace(".", "-")),
                         ("__MEASURE__", measure), ("__DIM__", dim_ref or ""),
                         ("__MLABEL__", m_label), ("__MLOWER__", in_sentence(m_label)),
                         ("__DLABEL__", d_label), ("__DLOWER__", in_sentence(d_label))):
        text = text.replace(token, value)
    return text
