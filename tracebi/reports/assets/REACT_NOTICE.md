# React lane — vendored assets & attribution

A report package whose page is `app.jsx` (the React lane) is built into one
offline HTML file that carries these bundles. The app's JSX is compiled in the
page by Sucrase and run as an inline script: the report's CSP still refuses
`eval`, and nothing is fetched.

| File | What it is | Inlined when |
|---|---|---|
| `react.min.js` | The runtime: TanStack Redact (a drop-in React runtime: the same API, smaller, synchronous rendering), Sucrase, the `tracebi` kit and the boot (`_react_src/runtime.js`, `kit.jsx`, `icons.js`) | every app.jsx page |
| `tailwind.min.js` | Tailwind CSS's browser build: generates the utility classes the app uses, in the page | every app.jsx page |
| `echarts-kit.min.js` | Apache ECharts for the kit's `<EChart>`, tree-shaken from `echarts/core` (`_react_src/echarts-entry.js`): bar, line, pie, scatter, effectScatter, radar, heatmap, treemap, sunburst, sankey, funnel, gauge, candlestick, boxplot, graph, parallel, themeRiver; dataset, grid, polar, tooltip, legend (scroll), title, dataZoom (slider, inside), brush, toolbox, visualMap, markLine / markPoint / markArea, axisPointer, aria; the canvas and SVG renderers. Loaded before the runtime, which registers it as the `echarts` module. | app.jsx imports `echarts`, or `EChart` (or `*`) from `tracebi` |
| `recharts.min.js` | Recharts 2, sharing the runtime's React (`react`, `react-dom`, `react/jsx-runtime` and `react-dom/client` all resolve to the page's one runtime) | app.jsx imports `recharts` |
| `lucide-icons.json` | Every lucide icon as data; the build embeds only the icons app.jsx imports | app.jsx imports `lucide-react` |

The template lane's `echarts.min.js` (`"libs": ["echarts"]`) is a different
build for a different consumer and is not used here.

## Third-party components

- **TanStack Redact** 0.2.1 — MIT — https://tanstack.com/redact
- **Sucrase** 3.35.0 — MIT — https://github.com/alangpierce/sucrase
- **Apache ECharts** 6.1.0 — Apache-2.0 — https://echarts.apache.org (bundles **zrender** 6.1.0, BSD-3-Clause, and **tslib** 2.3.0, 0BSD)
- **Recharts** 2.15.4 — MIT — https://recharts.org (bundles its MIT/ISC dependencies, among them react-smooth, recharts-scale, lodash, eventemitter3, react-is and victory-vendor's d3 modules)
- **Tailwind CSS** 4.1.11 browser build — MIT — https://tailwindcss.com
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
npm run build      # writes ../react.min.js, ../recharts.min.js, ../echarts-kit.min.js, ../tailwind.min.js, ../lucide-icons.json
```

A rebuild does not change what a page claims: these bundles only draw. A
checked figure (a kit figure, or an `<EChart>` of a binding's columns) shows
the embedded, fingerprinted bindings, filled or re-run by `tracebi.js`
exactly as in a template page.
