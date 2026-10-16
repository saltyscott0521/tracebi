// Rebuild the React lane's vendored bundles into ../ (see ../REACT_NOTICE.md).
import { build } from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";
import { icons } from "lucide";

const pkg = (n) => JSON.parse(readFileSync(`node_modules/${n}/package.json`, "utf8")).version;
const define = { "process.env.NODE_ENV": '"production"' };
const out = (f) => new URL(`../${f}`, import.meta.url).pathname;

await build({
  entryPoints: ["runtime.js"], bundle: true, minify: true, format: "iife", define,
  jsx: "transform", jsxFactory: "React.createElement", jsxFragment: "React.Fragment",
  banner: { js: `/*! TraceBi-credit: React ${pkg("react")} (MIT), ReactDOM ${pkg("react-dom")} (MIT), Sucrase ${pkg("sucrase")} (MIT) */` },
  outfile: out("react.min.js"),
});

const globals = {
  name: "react-globals",
  setup(b) {
    b.onResolve({ filter: /^react$/ }, () => ({ path: new URL("react-global.js", import.meta.url).pathname }));
    b.onResolve({ filter: /^react-dom$/ }, () => ({ path: new URL("react-dom-global.js", import.meta.url).pathname }));
  },
};
await build({
  entryPoints: ["recharts-entry.js"], bundle: true, minify: true, format: "iife", define,
  plugins: [globals],
  banner: { js: `/*! TraceBi-credit: Recharts ${pkg("recharts")} (MIT) */` },
  outfile: out("recharts.min.js"),
});

writeFileSync(out("tailwind.min.js"),
  `/*! TraceBi-credit: Tailwind CSS ${pkg("@tailwindcss/browser")} browser build (MIT) */\n` +
  readFileSync("node_modules/@tailwindcss/browser/dist/index.global.js", "utf8"));

// Icons as data: the build embeds only the ones a report imports.
const nodes = {};
for (const [name, node] of Object.entries(icons)) nodes[name] = node[2];  // children only
writeFileSync(out("lucide-icons.json"), JSON.stringify({ version: pkg("lucide"), icons: nodes }));
console.log("built react.min.js, recharts.min.js, tailwind.min.js, lucide-icons.json");
