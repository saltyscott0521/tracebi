// The React lane's runtime: one React, the TraceBi kit, and the boot that
// runs the report's app.jsx and mounts it.
//
// The build compiles app.jsx once (tracebi/reports/app_lane.py compile_app):
// the page carries the result as a plain script (#tracebi-app) that defines
// window.__tbApp(module, exports, require), and nothing is compiled here.
// Where the build could not compile it, the page carries the source as a JSON
// string (#tracebi-app) and the same compiler (sucrase.min.js,
// window.__tbSucrase), which compiles it here and runs it as an inline script:
// the page's CSP allows inline scripts and still refuses eval. Imports resolve
// only to the modules registered below; the build has already refused any other.
import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as jsxRuntime from "react/jsx-runtime";
import * as kit from "./kit.jsx";
import { lucideModule } from "./icons.js";

const modules = (window.__tbModules = window.__tbModules || {});
Object.assign(modules, {
  react: React,
  "react-dom": ReactDOM,
  "react-dom/client": ReactDOMClient,
  "react/jsx-runtime": jsxRuntime,
  tracebi: kit,
  "lucide-react": lucideModule(),
});
// ECharts (echarts-kit.min.js) is inlined before this bundle on a page that
// imports "echarts" or the kit's <EChart>; it never imports React.
if (window.__tbECharts) modules.echarts = window.__tbECharts;

window.__tbRequire = function (name) {
  const m = modules[name];
  if (!m) {
    throw new Error(`"${name}" is not in the TraceBi kit. ` +
      `Import from: ${Object.keys(modules).sort().join(", ")}.`);
  }
  return m;
};

function readJson(id) {
  const el = document.getElementById(id);
  return el ? JSON.parse(el.textContent) : null;
}

function showError(host, err) {
  const box = document.createElement("div");
  box.className = "tb-app-error";
  box.setAttribute("role", "alert");
  const h = document.createElement("strong");
  h.textContent = "This report's app could not start.";
  const p = document.createElement("pre");
  p.textContent = String((err && err.message) || err);
  box.appendChild(h);
  box.appendChild(p);
  host.appendChild(box);
}

class Boundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return React.createElement("div", { className: "tb-app-error", role: "alert" },
      React.createElement("strong", null, "This report's app stopped with an error."),
      React.createElement("pre", null, String(this.state.error.message || this.state.error)));
  }
}

function start() {
  const host = document.getElementById("tb-app");
  if (!host) return;
  let App;
  try {
    if (typeof window.__tbApp !== "function") {
      // Compiled in the page: the build could not compile it.
      const source = readJson("tracebi-app");
      if (typeof source !== "string") return;
      if (!window.__tbSucrase) throw new Error("This page carries no app.jsx compiler.");
      const script = document.createElement("script");
      script.textContent = "window.__tbApp=function(module,exports,require){\n" +
        window.__tbSucrase.compile(source) + "\n};";
      document.head.appendChild(script);
    }
    const mod = { exports: {} };
    window.__tbApp(mod, mod.exports, window.__tbRequire);
    App = (mod.exports || {}).default;
    if (typeof App !== "function") {
      throw new Error("app.jsx must `export default` a component.");
    }
  } catch (err) {
    showError(host, err);
    return;
  }
  // The build's no-JavaScript view (the figures as built) gives way to the
  // app; it stays only when the app cannot start.
  while (host.firstChild) host.removeChild(host.firstChild);
  const root = ReactDOMClient.createRoot(host);
  // Synchronous first render: every kit figure exists before the runtime's
  // first hydration pass, so the receipt and the badges find them.
  ReactDOM.flushSync(() => {
    root.render(React.createElement(Boundary, null, React.createElement(App)));
  });
}

function boot() {
  if (window.tracebi && typeof window.tracebi.ready === "function") window.tracebi.ready(start);
  else start();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
