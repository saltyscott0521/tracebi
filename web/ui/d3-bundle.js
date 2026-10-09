// The D3 subset TraceBi reports inline, exposed as a global `d3`. Built to an
// IIFE and inlined into self-contained report files (offline, no CDN, no
// eval). d3-dsv and d3-fetch are left out on purpose: dsv parses with
// `new Function` (the report CSP forbids eval) and a report reads its rows
// from tracebi.data(), never the network.
export * from 'd3-array';
export * from 'd3-axis';
export * from 'd3-brush';
export * from 'd3-color';
export * from 'd3-format';
export * from 'd3-hierarchy';
export * from 'd3-interpolate';
export * from 'd3-path';
export * from 'd3-scale';
export * from 'd3-selection';
export * from 'd3-shape';
export * from 'd3-time';
export * from 'd3-time-format';
export * from 'd3-transition';
export * from 'd3-ease';
