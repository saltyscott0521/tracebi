// Rebuild the vendored page engine into ../tracebi-calc.js (see ../CALC_NOTICE.md).
//
// The banner records a SHA-256 over this directory's sources, so
// tests/test_engine_assets.py can tell a bundle that was not rebuilt after a
// source edit without running node or npm.
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export const SOURCES = ["build.mjs", "engine.js", "index.js", "package.json", "parquet.js", "select.js"];

const here = (f) => new URL(f, import.meta.url).pathname;
const hash = createHash("sha256");
for (const f of SOURCES) {
  hash.update(f + "\n");
  hash.update(readFileSync(here(f)));
}
const pkg = (n) => JSON.parse(readFileSync(here(`node_modules/${n}/package.json`), "utf8")).version;

await build({
  entryPoints: [here("index.js")], bundle: true, minify: true, format: "iife",
  target: "es2020", legalComments: "none",
  banner: { js: `/*! TraceBi-credit: tracebi-calc, hyparquet ${pkg("hyparquet")} (MIT) | src-sha256:${hash.digest("hex")} */` },
  outfile: here("../tracebi-calc.js"),
});
console.log("built tracebi-calc.js");
