// Apache ECharts for the kit's <EChart> (echarts-kit.min.js): one tree-shaken
// build of echarts/core with the series and components below, both renderers.
// It never imports React (it draws into its own div), so it needs no globals
// plugin; runtime.js registers it as the "echarts" module an app.jsx imports.
// The template lane's echarts.min.js ("libs": ["echarts"]) is a different
// build for a different consumer and stays as it is.
import * as echarts from "echarts/core";
import {
  BarChart, LineChart, PieChart, ScatterChart, EffectScatterChart, RadarChart,
  HeatmapChart, TreemapChart, SunburstChart, SankeyChart, FunnelChart, GaugeChart,
  CandlestickChart, BoxplotChart, GraphChart, ParallelChart, ThemeRiverChart,
} from "echarts/charts";
import {
  DatasetComponent, GridComponent, PolarComponent, RadarComponent,
  ParallelComponent, SingleAxisComponent, TooltipComponent,
  LegendScrollComponent, TitleComponent, DataZoomSliderComponent, DataZoomInsideComponent,
  BrushComponent, ToolboxComponent, VisualMapComponent, MarkLineComponent,
  MarkPointComponent, MarkAreaComponent, AxisPointerComponent, AriaComponent,
} from "echarts/components";
import { CanvasRenderer, SVGRenderer } from "echarts/renderers";

echarts.use([
  BarChart, LineChart, PieChart, ScatterChart, EffectScatterChart, RadarChart,
  HeatmapChart, TreemapChart, SunburstChart, SankeyChart, FunnelChart, GaugeChart,
  CandlestickChart, BoxplotChart, GraphChart, ParallelChart, ThemeRiverChart,
  DatasetComponent, GridComponent, PolarComponent, RadarComponent,
  ParallelComponent, SingleAxisComponent, TooltipComponent,
  LegendScrollComponent, TitleComponent, DataZoomSliderComponent, DataZoomInsideComponent,
  BrushComponent, ToolboxComponent, VisualMapComponent, MarkLineComponent,
  MarkPointComponent, MarkAreaComponent, AxisPointerComponent, AriaComponent,
  CanvasRenderer, SVGRenderer,
]);

window.__tbECharts = echarts;
