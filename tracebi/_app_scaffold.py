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
import { Masthead, Footer, Kpi, Value, Spark, Chart, Table, Filter, Search, Download,
         Segmented, useUrlState, usePrinting } from "tracebi";

const TITLE = "__TITLE__";
const VIEWS = { Overview: LayoutDashboard, Detail: Table2 };
'''

_APP_HEADERS = {
    "left": '''
function Header() {
  // The masthead: the title, what this page is for, when it was built and the
  // verdict chip (from the file's receipt). period="…" names what the numbers cover.
  return <Masthead title={TITLE}>One line on what this page is for.</Masthead>;
}
''',
    "center": '''
function Header() {
  return (
    <Masthead title={TITLE} data-tb-title="center">
      One line on what this page is for.
    </Masthead>
  );
}
''',
    "banner": '''
function Header() {
  return (
    <Masthead title={TITLE} data-tb-title="banner">
      One line on what this page is for.
    </Masthead>
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
      {/* The 12-column grid: a wide panel (8) beside a narrow one (4), the
          breakdown and its ranking; one column on a phone. */}
      <div className="tb-grid">
        <section className="tb-card tb-span-8">
          <h2>__MLABEL__ by __DLABEL__</h2>
          <p className="tb-note">Largest first.</p>
          <Chart binding="breakdown" type="bar" x="__DIM__" y="__MEASURE__"
                 valueFormat="compact" />
        </section>
        <section className="tb-card tb-span-4">
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
      <div className="tb-grid">
        <section className="tb-card tb-span-6">
          <h2>Top ten</h2>
          <Chart binding="top10" type="barh" x="__DIM__" y="__MEASURE__" valueFormat="compact" />
        </section>
        <section className="tb-card tb-span-6">
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
      <main className="tb-page space-y-8 px-6 py-8">
        <Header />
        <Overview />
        <Detail />
        <Footer />
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
  // Printed (Ctrl+P, or the PDF build), the page holds every view.
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink">
      <main className="tb-page space-y-8 px-6 py-8">
        <Header />
        <nav className="flex gap-1 border-b border-rule print:hidden">
          {Object.entries(VIEWS).map(([name, Icon]) => (
            <button key={name} onClick={() => setView(name)}
              className={"flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm " +
                (view === name ? "border-accent font-medium text-ink"
                               : "border-transparent text-muted hover:text-ink")}>
              <Icon size={15} />{name}
            </button>
          ))}
        </nav>
        {printing ? <><Overview /><Detail /></> : <View />}
        <Footer />
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
  // Printed (Ctrl+P, or the PDF build), the page holds every view.
  const printing = usePrinting();
  return (
    <div className="min-h-screen bg-page text-ink md:flex">
      <aside className="shrink-0 border-b border-rule bg-card p-3 md:sticky md:top-0
                        md:h-screen md:w-60 md:border-r md:border-b-0 print:hidden">
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
      <main className="min-w-0 flex-1 space-y-8 px-6 py-8">
__MAIN_HEADER__
        {printing ? <><Overview /><Detail /></> : <View />}
        <Footer />
      </main>
    </div>
  );
}
''',
}

_BRAND_PLAIN = '''        <div className="mb-3 border-b border-rule px-2.5 pb-3 font-semibold">{TITLE}</div>'''
_BRAND_TITLE = '''        <Masthead title={TITLE} data-tb-title="nav" className="mb-3 border-b border-rule px-2.5 pb-3">
          One line on what this page is for.
        </Masthead>'''


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


def funnel_rates(stages):
    """The report-level conversion measures a funnel declares: for every stage
    after the first, ``(name, stage)`` — the share of the first stage that
    reaches it. One naming rule, shared by report.json and app.jsx."""
    return [(f"{s}_conversion", s) for s in stages[1:]]


def _funnel_views(stages, dim_ref, humanise):
    """Each stage widest first, how much of the first reaches it (report-level
    ratio measures, so the receipt names them), and where it narrows by the
    category."""
    first = in_sentence(humanise(stages[0]))
    rates = funnel_rates(stages)
    last_rate, last = rates[-1]
    stage_kpis = "\n".join(
        f'        <Kpi{" lead" if i == 0 else ""} binding="stages" cell="{s}" '
        f'label="{humanise(s)}"' + (' context="the top of the funnel"' if i == 0 else "") + " />"
        for i, s in enumerate(stages))
    rate_kpis = "\n".join(
        f'        <Kpi binding="stages" cell="{r}" label="{humanise(s)}, % of {first}" />'
        for r, s in rates)
    by_cat = (f'''
      <div className="tb-grid">
        <section className="tb-card tb-span-8">
          <h2>Where it narrows</h2>
          <p className="tb-note">{humanise(last)} as a share of {first}, by {in_sentence(humanise(dim_ref))}.</p>
          <Chart binding="breakdown" type="barh" x="{dim_ref}" y="{last_rate}" valueFormat="percent" />
        </section>
        <section className="tb-card tb-span-4">
          <h2>Conversion by {in_sentence(humanise(dim_ref))}</h2>
          <Table binding="breakdown" columns={{["{dim_ref}", "{last_rate}"]}} sort bars="{last_rate}" />
        </section>
      </div>''' if dim_ref else "")
    detail = (f'''
function Detail() {{
  return (
    <section className="tb-card">
      <h2>Every {in_sentence(humanise(dim_ref))}</h2>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Search binding="breakdown" />
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
      <Table binding="stages" />
    </section>
  );
}
''')
    return (f'''
// A funnel: each stage, widest first, then how much of the first reaches it.
// The stages are report.json's "stages" measures (put them in your funnel's
// order); each conversion is a report-level ratio in its "measures" block, so
// the receipt names it. Never divide in this file.
function Overview() {{
  return (
    <>
      <p className="tb-lede">
        <Value binding="stages" cell="{last_rate}" id="lede-conversion" /> of {first} reach{{" "}}
        {in_sentence(humanise(last))}. Rewrite this sentence as the page's finding.
      </p>
      <div className="tb-grid">
{stage_kpis}
      </div>
      <h2 className="text-[0.95em] font-semibold">Conversion</h2>
      <div className="tb-grid">
{rate_kpis}
      </div>''' + by_cat + '''
    </>
  );
}
''' + detail)


def _monitor_views(measures, dim_ref, time_ref, humanise):
    """The latest period of every measure, each with its trend, and a watch
    list (the lowest members first) beside the trend."""
    period = in_sentence(humanise(time_ref))
    kpis = "\n".join(
        f'        <Kpi{" lead" if i == 0 else ""} binding="latest" cell="{m}" '
        f'label="{humanise(m)}">\n'
        f'          <Spark binding="by_period" x="{time_ref}" y="{m}" valueFormat="compact" />\n'
        f'        </Kpi>'
        for i, m in enumerate(measures))
    m0 = humanise(measures[0])
    trend = f'''
          <h2>{m0} by {period}</h2>
          <Chart binding="by_period" type="line" x="{time_ref}" y="{measures[0]}" valueFormat="compact" />'''
    watch = (f'''
      <div className="tb-grid">
        <section className="tb-card tb-span-4">
          <h2>Watch list</h2>
          <p className="tb-note">Lowest {in_sentence(m0)} first: where to look.</p>
          <Table binding="watch" bars="{measures[0]}" />
        </section>
        <section className="tb-card tb-span-8">{trend}
        </section>
      </div>''' if dim_ref else f'''
      <section className="tb-card">{trend}
      </section>''')
    binding = "breakdown" if dim_ref else "by_period"
    filt = (f'\n        <Filter binding="breakdown" column="{dim_ref}" label="{humanise(dim_ref)}" />'
            if dim_ref else "")
    every = in_sentence(humanise(dim_ref)) if dim_ref else period
    return (f'''
// A monitor: is anything off right now? The latest {period} of each measure
// with its trend, and the lowest members first. The header says when it was built.
function Overview() {{
  return (
    <>
      <p className="text-sm text-muted">
        Latest {period}: <Value binding="latest" cell="{time_ref}" id="latest-period" />.
      </p>
      <div className="tb-grid">
{kpis}
      </div>''' + watch + f'''
    </>
  );
}}

function Detail() {{
  return (
    <section className="tb-card">
      <h2>Every {every}</h2>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Search binding="{binding}" />{filt}
        <Download binding="{binding}" />
      </div>
      <Table binding="{binding}" id="detail-table" sort rows="all" />
    </section>
  );
}}
''')


def report_app_jsx(title, measure, dim_ref, *, nav="", title_at="left",
                   humanise=lambda s: s, job="overview", measures=None, time_ref=None):
    """The React-lane starter: one app.jsx over the scaffold's bindings,
    shaped by the job (overview: totals/top/breakdown; trend: totals/latest/
    by_period, with dim_ref the period; leaderboard: totals/top/ranking/top10;
    scorecard: totals/breakdown/by_period; monitor: latest/by_period/watch/
    breakdown; funnel: stages/breakdown) and the look the builder chose."""
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
                          "        <Header view={printing ? TITLE : view} />" if in_nav else "        <Header />")
    if job == "monitor" and not time_ref:
        job = "scorecard"           # no time dimension: the measures at a glance
    if job == "funnel" and len(measures or []) < 2:
        job = "overview"            # one measure is not a funnel
    if job == "scorecard":
        views = _scorecard_views(measures or [measure], dim_ref, time_ref, humanise)
    elif job == "monitor":
        views = _monitor_views(measures, dim_ref, time_ref, humanise)
    elif job == "funnel":
        views = _funnel_views(measures, dim_ref, humanise)
    else:
        views = (_APP_VIEWS_TOTALS if not dim_ref else
                 {"trend": _APP_VIEWS_TREND, "leaderboard": _APP_VIEWS_LEADERBOARD}.get(
                     job, _APP_VIEWS_DIM))
    head = _APP_HEAD
    if not nav:
        head = head.replace('import { LayoutDashboard, Table2 } from "lucide-react";\n', "")
        head = head.replace("const VIEWS = { Overview: LayoutDashboard, Detail: Table2 };\n", "")
        head = head.replace("useUrlState, usePrinting }", "useUrlState }")
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
