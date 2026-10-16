// The React lane's runtime: one React, the JSX compiler, the TraceBi kit, and
// the boot that compiles the report's app.jsx in the page and mounts it.
//
// The app source rides in the page as a JSON string (#tracebi-app). It is
// compiled here, in the browser, and run as an inline script — the page's CSP
// allows inline scripts and still refuses eval. Imports resolve only to the
// modules registered below; the build has already refused any other.
import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as jsxRuntime from "react/jsx-runtime";
import { transform } from "sucrase";
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
  const source = readJson("tracebi-app");
  if (!host || typeof source !== "string") return;
  let App;
  try {
    const code = transform(source, {
      transforms: ["jsx", "typescript", "imports"],
      jsxRuntime: "automatic",
      production: true,
      filePath: "app.jsx",
    }).code;
    window.__tbAppModule = null;
    window.__tbAppError = null;
    const script = document.createElement("script");
    script.textContent =
      "(function(){var module={exports:{}},exports=module.exports,require=window.__tbRequire;" +
      "try{\n" + code + "\n;window.__tbAppModule=module.exports;}catch(e){window.__tbAppError=e;}})();";
    document.head.appendChild(script);
    if (window.__tbAppError) throw window.__tbAppError;
    const mod = window.__tbAppModule || {};
    App = mod.default;
    if (typeof App !== "function") {
      throw new Error("app.jsx must `export default` a component.");
    }
  } catch (err) {
    showError(host, err);
    return;
  }
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
