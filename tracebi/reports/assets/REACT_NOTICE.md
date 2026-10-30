# React lane — vendored assets & attribution

A report package whose page is `app.jsx` (the React lane) is built into one
offline HTML file that carries these bundles. `tracebi report build` compiles
the app once: Sucrase turns its JSX into plain JavaScript and Tailwind's
compiler writes the CSS for the classes its source names, both run in an
embedded V8 (`mini-racer`, in the `reports` extra), so no Node is needed. The
page carries the compiled script and the CSS, not the compilers; the
manifest's `app_compile` says `"at": "build"`. Where the build cannot run them
(mini-racer not installed), the page carries the source, Sucrase and
Tailwind's browser build and does the same work in the reader's browser
(`"at": "page"`, with the reason). Either way the report's CSP still refuses
`eval`, and nothing is fetched.

| File | What it is | Inlined when |
|---|---|---|
| `react.min.js` | The runtime: TanStack Redact (a drop-in React runtime: the same API, smaller, synchronous rendering), the `tracebi` kit and the boot (`_react_src/runtime.js`, `kit.jsx`, `icons.js`) | every app.jsx page |
| `sucrase.min.js` | The app.jsx compiler: Sucrase with the lane's one set of options (`_react_src/sucrase-entry.js`), run at build | only a page the build could not compile |
| `tailwind-compiler.min.js` | Tailwind CSS's compiler and its stylesheets (`_react_src/tailwind-entry.js`), run at build to generate the CSS for the classes app.jsx names | never: the page carries the CSS it wrote |
| `tailwind.min.js` | Tailwind CSS's browser build: generates the utility classes the app uses, in the page | only a page the build could not compile |
| `echarts-kit.min.js` | Apache ECharts, which draws every chart (tracebi.js's chart engine, the kit's `<Chart>`, `<Spark>` and `<EChart>`, a template's `{{ figure() }}` charts), tree-shaken from `echarts/core` (`_react_src/echarts-entry.js`) to what the option builder draws, what the shipped reports draw and what the guides name: bar, line, scatter, effectScatter, pictorialBar, pie, funnel, treemap, sunburst, heatmap, sankey; grid, tooltip, axisPointer, title, legend, markLine / markPoint / markArea, aria, visualMap, dataZoom (slider), brush, toolbox; the canvas and SVG renderers. Anything else (radar, gauge, candlestick, boxplot, graph, parallel, themeRiver, polar, dataset, …) is not in it (ECharts draws nothing for it, silently): add it to the entry and rebuild. Loaded before the runtime, which registers it as the `echarts` module. | any page with a chart figure (a template's too); an app.jsx that imports `echarts`, or `Chart`, `Spark` or `EChart` (or `*`) from `tracebi` |
| `recharts.min.js` | Recharts 2, sharing the runtime's React (`react`, `react-dom`, `react/jsx-runtime` and `react-dom/client` all resolve to the page's one runtime) | app.jsx imports `recharts` |
| `lucide-icons.json` | Every lucide icon as data; the build embeds only the icons app.jsx imports | app.jsx imports `lucide-react` |

Tailwind at build reads app.jsx's text, as Tailwind's CLI reads a source: a
class name the app assembles at run time from pieces (`"text-" + tone`) is
not seen, so write each class whole.

There is one ECharts build: a template page with a chart carries this same
`echarts-kit.min.js` (the older `echarts.min.js` and `"libs": ["echarts"]`
are gone). `d3.min.js` stays only for an author's own `tracebi.draw` figures
(`"libs": ["d3"]`).

## Third-party components

- **TanStack Redact** 0.2.1 — MIT — https://tanstack.com/redact
- **Sucrase** 3.35.0 — MIT — https://github.com/alangpierce/sucrase
- **Apache ECharts** 6.1.0 — Apache-2.0 — https://echarts.apache.org (bundles **zrender** 6.1.0, BSD-3-Clause, and **tslib** 2.3.0, 0BSD)
- **Recharts** 2.15.4 — MIT — https://recharts.org (bundles its MIT/ISC dependencies, among them react-smooth, recharts-scale, lodash, eventemitter3, react-is and victory-vendor's d3 modules)
- **Tailwind CSS** 4.1.11 compiler and browser build — MIT — https://tailwindcss.com
- **Lucide** 0.468.0 icons — ISC — https://lucide.dev

## Why one runtime, and why Recharts 2

Every app.jsx page runs on Redact; there is no React 18 bundle any more.
ECharts draws into its own div and never imports React, so the runtime
cannot affect it. Recharts 2.15.4 renders on Redact. Recharts 3 does not:
Redact re-renders children that React 18 would skip, and Recharts 3's
per-series store registration then loops, so the page hangs on its first
commit. Recharts stays importable as the compatibility path for authors who
know its JSX; `<EChart>` is the chart.

## Rebuilding

```
cd tracebi/reports/assets/_react_src
npm ci
npm run build      # writes ../react.min.js, ../sucrase.min.js, ../tailwind-compiler.min.js,
                   #   ../recharts.min.js, ../echarts-kit.min.js, ../tailwind.min.js, ../lucide-icons.json
```

A rebuild does not change what a page claims: these bundles only draw. A
checked figure (a kit figure, or an `<EChart>` of a binding's columns) shows
the embedded, fingerprinted bindings, filled or re-run by `tracebi.js`
exactly as in a template page.
