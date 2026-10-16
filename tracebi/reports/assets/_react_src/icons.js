// lucide-react, from data. The build embeds only the icons app.jsx imports
// (#tracebi-icons: {Name: [[tag, attrs], ...]}); each becomes a component
// with lucide-react's props (size, color, strokeWidth, className).
import * as React from "react";

let data = null;
function iconData() {
  if (data === null) {
    const el = document.getElementById("tracebi-icons");
    data = el ? JSON.parse(el.textContent) : {};
  }
  return data;
}

const kebab = (s) => s.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
const reactAttrs = (attrs) => {
  const out = {};
  for (const k in attrs) out[k.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = attrs[k];
  return out;
};

function makeIcon(name, node) {
  const Icon = React.forwardRef(function Icon(
    { size = 24, color = "currentColor", strokeWidth = 2, absoluteStrokeWidth,
      className = "", children, ...rest }, ref) {
    const width = absoluteStrokeWidth ? (Number(strokeWidth) * 24) / Number(size) : strokeWidth;
    return React.createElement("svg", {
      ref, xmlns: "http://www.w3.org/2000/svg", width: size, height: size,
      viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth: width,
      strokeLinecap: "round", strokeLinejoin: "round",
      className: ["lucide", "lucide-" + kebab(name), className].filter(Boolean).join(" "),
      "aria-hidden": rest["aria-label"] ? undefined : "true",
      ...rest,
    }, ...node.map(([tag, attrs], i) => React.createElement(tag, { key: i, ...reactAttrs(attrs) })),
    children);
  });
  Icon.displayName = name;
  return Icon;
}

export function lucideModule() {
  const cache = {};
  return new Proxy({}, {
    get(_, name) {
      if (typeof name !== "string") return undefined;
      if (name === "__esModule") return true;
      if (cache[name]) return cache[name];
      const base = name.endsWith("Icon") && !iconData()[name] ? name.slice(0, -4) : name;
      const node = iconData()[base];
      if (!node) return undefined;
      return (cache[name] = makeIcon(base, node));
    },
  });
}
