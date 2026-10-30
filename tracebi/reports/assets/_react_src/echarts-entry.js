// Apache ECharts (echarts-kit.min.js): one tree-shaken build of echarts/core
// with the series and components below, both renderers. It draws every chart
// on every page: tracebi.js's chart engine (a template's figures, the kit's
// <Chart>, <Spark> and <EChart>) and an app's option-only <EChart>. It never
// imports React (it draws into its own div), so it needs no globals plugin;
// runtime.js registers it as the "echarts" module an app.jsx imports.
//
// What is in it, and why (REACT_NOTICE.md keeps the same list):
// - every series the option builder (tracebi.js optionFor) draws: bar, line,
//   scatter, effectScatter, pictorialBar (axis charts); pie, funnel, treemap,
//   sunburst (name/value items);
// - the series the shipped reports draw through an option: heatmap (the
//   showcase) and sankey (the desk);
// - the components the option builder uses: grid, tooltip, axisPointer,
//   title, markLine, markPoint, aria; and the ones the guides name for a
//   configureChart patch or an <EChart option>: legend, dataZoom (the
//   slider), brush, visualMap, markArea, toolbox;
// - the canvas and SVG renderers.
// Anything else (radar, gauge, candlestick, boxplot, graph, parallel,
// themeRiver, polar, dataset, …) is left out, and this production build draws
// nothing for a series or component it lacks, silently. Add it here and
// rebuild (npm run build).
import * as echarts from "echarts/core";
import {
  BarChart, LineChart, ScatterChart, EffectScatterChart, PictorialBarChart,
  PieChart, FunnelChart, TreemapChart, SunburstChart, HeatmapChart, SankeyChart,
} from "echarts/charts";
import {
  GridComponent, TooltipComponent, AxisPointerComponent, TitleComponent,
  MarkLineComponent, MarkPointComponent, AriaComponent,
  LegendComponent, DataZoomSliderComponent, BrushComponent, VisualMapComponent,
  MarkAreaComponent, ToolboxComponent,
} from "echarts/components";
import { CanvasRenderer, SVGRenderer } from "echarts/renderers";

echarts.use([
  BarChart, LineChart, ScatterChart, EffectScatterChart, PictorialBarChart,
  PieChart, FunnelChart, TreemapChart, SunburstChart, HeatmapChart, SankeyChart,
  GridComponent, TooltipComponent, AxisPointerComponent, TitleComponent,
  MarkLineComponent, MarkPointComponent, AriaComponent,
  LegendComponent, DataZoomSliderComponent, BrushComponent, VisualMapComponent,
  MarkAreaComponent, ToolboxComponent,
  CanvasRenderer, SVGRenderer,
]);

window.__tbECharts = echarts;
