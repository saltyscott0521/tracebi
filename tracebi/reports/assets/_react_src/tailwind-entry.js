// Tailwind at build (tailwind-compiler.min.js): Tailwind CSS's own compiler
// and its four stylesheets, as one bundle `tracebi report build` runs in an
// embedded V8 (tracebi/reports/app_lane.py compile_app). It turns the class
// names an app.jsx's source carries into the static CSS for exactly those
// utilities. Never inlined into a page: a built page carries the CSS, not
// Tailwind. It resolves the same stylesheets the browser build does.
import { compile } from "tailwindcss";
import index from "tailwindcss/index.css";
import preflight from "tailwindcss/preflight.css";
import theme from "tailwindcss/theme.css";
import utilities from "tailwindcss/utilities.css";

const sheets = {
  tailwindcss: index,
  "tailwindcss/preflight": preflight, "tailwindcss/preflight.css": preflight, "./preflight.css": preflight,
  "tailwindcss/theme": theme, "tailwindcss/theme.css": theme, "./theme.css": theme,
  "tailwindcss/utilities": utilities, "tailwindcss/utilities.css": utilities, "./utilities.css": utilities,
};

async function loadStylesheet(id, base) {
  if (!Object.prototype.hasOwnProperty.call(sheets, id)) {
    throw new Error(`@import "${id}" is not available at build`);
  }
  return { path: `virtual:${id}`, base, content: sheets[id] };
}

async function loadModule() {
  throw new Error("Tailwind plugins and config files are not available at build.");
}

globalThis.__tbTailwind = {
  // css: the input stylesheet; candidates: every token that may be a class.
  // Settles into __tbTailwind.result (or .error): the caller reads it after
  // the engine has run the promise's jobs.
  build(css, candidates) {
    this.result = this.error = null;
    compile(css, { base: "/", loadStylesheet, loadModule })
      .then((compiler) => { this.result = compiler.build(candidates); })
      .catch((err) => { this.error = String((err && err.message) || err); });
  },
};
