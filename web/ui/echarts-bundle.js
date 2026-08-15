// Tree-shaken ECharts bundle for TraceBi reports: only the chart types and
// components a BI report needs, exposed as a global `echarts`. Built to an IIFE
// and inlined into self-contained report files (offline, no CDN, no eval).
import * as echarts from 'echarts/core';
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  DataZoomComponent, DatasetComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
echarts.use([
  BarChart, LineChart, PieChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  DataZoomComponent, DatasetComponent, CanvasRenderer,
]);
window.echarts = echarts;
