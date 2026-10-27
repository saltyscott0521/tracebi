# React lane — vendored assets & attribution

A report package whose page is `app.jsx` (the React lane) is built into one
offline HTML file that carries these bundles. The app's JSX is compiled in the
page by Sucrase and run as an inline script: the report's CSP still refuses
`eval`, and nothing is fetched.

| File | What it is | Inlined when |
|---|---|---|
| `react.min.js` | TanStack Redact (a drop-in React runtime: the same API, smaller, synchronous rendering), Sucrase, the `tracebi` kit and the boot (`_react_src/runtime.js`, `kit.jsx`, `icons.js`) | every app.jsx page that does not import `recharts` |
| `react18.min.js` | The same bundle on React 18 and ReactDOM | app.jsx imports `recharts` (a Recharts chart locks the page under Redact) |
| `tailwind.min.js` | Tailwind CSS's browser build: generates the utility classes the app uses, in the page | every app.jsx page |
| `recharts.min.js` | Recharts, sharing the kit's React | app.jsx imports `recharts` |
| `lucide-icons.json` | Every lucide icon as data; the build embeds only the icons app.jsx imports | app.jsx imports `lucide-react` |

## Third-party components

- **TanStack Redact** 0.2.1 — MIT — https://tanstack.com/redact
- **React** and **ReactDOM** 18.3.1 — MIT — https://react.dev
- **Sucrase** 3.35.0 — MIT — https://github.com/alangpierce/sucrase
- **Recharts** 3.1.2 — MIT — https://recharts.org (bundles its MIT/ISC dependencies, among them Redux Toolkit, Immer, Reselect, eventemitter3 and victory-vendor's d3 modules)
- **Tailwind CSS** 4.1.11 browser build — MIT — https://tailwindcss.com
- **Lucide** 0.468.0 icons — ISC — https://lucide.dev

## Rebuilding

```
cd tracebi/reports/assets/_react_src
npm ci
npm run build      # writes ../react.min.js, ../react18.min.js, ../recharts.min.js, ../tailwind.min.js, ../lucide-icons.json
```

The receipt is unaffected by a rebuild: these bundles only draw. The numbers a
kit figure shows come from the embedded, fingerprinted bindings, filled by
`tracebi.js` exactly as in a template page.
