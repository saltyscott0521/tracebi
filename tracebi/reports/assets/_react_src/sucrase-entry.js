// The app.jsx compiler (sucrase.min.js): Sucrase, with the one set of options
// every app page is compiled with. `tracebi report build` runs it once, at
// build, in an embedded V8 (tracebi/reports/app_lane.py compile_app); a page
// built where that is impossible inlines this same bundle and runs it in the
// page instead (runtime.js). One compiler, one set of options, one output.
import { transform } from "sucrase";

globalThis.__tbSucrase = {
  compile(source) {
    return transform(source, {
      transforms: ["jsx", "typescript", "imports"],
      jsxRuntime: "automatic",
      production: true,
      filePath: "app.jsx",
    }).code;
  },
};
