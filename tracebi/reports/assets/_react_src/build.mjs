// Rebuild the React lane's vendored bundles into ../ (see ../REACT_NOTICE.md).
import { build } from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";
import { icons } from "lucide";

const pkg = (n) => JSON.parse(readFileSync(`node_modules/${n}/package.json`, "utf8")).version;
const define = { "process.env.NODE_ENV": '"production"' };
// The kit's React is TanStack Redact (react.min.js): the same API, a smaller
// runtime, synchronous rendering. It is the one runtime: Recharts 2 renders on
// it (Recharts 3 does not), and ECharts never imports React at all.
const redact = {
  react: "@tanstack/redact",
  "react/jsx-runtime": "@tanstack/redact/jsx-runtime",
  "react-dom": "@tanstack/redact/dom",
  "react-dom/client": "@tanstack/redact/dom-client",
};
const out = (f) => new URL(`../${f}`, import.meta.url).pathname;
const here = (f) => new URL(f, import.meta.url).pathname;

await build({
  entryPoints: ["runtime.js"], bundle: true, minify: true, format: "iife", define,
  jsx: "transform", jsxFactory: "React.createElement", jsxFragment: "React.Fragment",
  alias: redact,
  banner: { js: `/*! TraceBi-credit: TanStack Redact ${pkg("@tanstack/redact")} (MIT), Sucrase ${pkg("sucrase")} (MIT) */` },
  outfile: out("react.min.js"),
});

// Recharts shares the page's one React: every React entry point it (or a
// dependency) imports resolves to the module the runtime registered. Without
// jsx-runtime and react-dom/client here, React 18's own copies get bundled.
const globals = {
  name: "react-globals",
  setup(b) {
    b.onResolve({ filter: /^react$/ }, () => ({ path: here("react-global.js") }));
    b.onResolve({ filter: /^react-dom$/ }, () => ({ path: here("react-dom-global.js") }));
    b.onResolve({ filter: /^react\/jsx-runtime$/ }, () => ({ path: here("jsx-runtime-global.js") }));
    b.onResolve({ filter: /^react-dom\/client$/ }, () => ({ path: here("react-dom-client-global.js") }));
  },
};
await build({
  entryPoints: ["recharts-entry.js"], bundle: true, minify: true, format: "iife", define,
  plugins: [globals],
  banner: { js: `/*! TraceBi-credit: Recharts ${pkg("recharts")} (MIT) */` },
  outfile: out("recharts.min.js"),
});

// ECharts for the kit's <EChart>: tree-shaken from echarts/core.
await build({
  entryPoints: ["echarts-entry.js"], bundle: true, minify: true, format: "iife", define,
  banner: { js: `/*! TraceBi-credit: Apache ECharts ${pkg("echarts")} (Apache-2.0), zrender ${pkg("zrender")} (BSD-3-Clause), tslib ${pkg("tslib")} (0BSD) */` },
  outfile: out("echarts-kit.min.js"),
});

writeFileSync(out("tailwind.min.js"),
  `/*! TraceBi-credit: Tailwind CSS ${pkg("@tailwindcss/browser")} browser build (MIT) */\n` +
  readFileSync("node_modules/@tailwindcss/browser/dist/index.global.js", "utf8"));

// Icons as data: the build embeds only the ones a report imports.
const nodes = {};
for (const [name, node] of Object.entries(icons)) nodes[name] = node[2];  // children only
writeFileSync(out("lucide-icons.json"), JSON.stringify({ version: pkg("lucide"), icons: nodes }));
console.log("built react.min.js, recharts.min.js, echarts-kit.min.js, tailwind.min.js, lucide-icons.json");
