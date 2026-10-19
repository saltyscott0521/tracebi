/* parquet.js — one embedded slice block decoded into typed columns.
 *
 * The reader is hyparquet (vendored, MIT; see ../CALC_NOTICE.md), used at its
 * synchronous core: the whole block is already in memory, so there is nothing
 * to fetch and no reason to make the page wait on a promise. Only the codecs
 * hyparquet decodes natively (Snappy and uncompressed pages) are accepted; a
 * block written with another codec fails here by name, which is what decision
 * 8 of the live-reports plan asks the build to guarantee never happens.
 *
 * The decoded table is columnar, because every engine step is a loop over one
 * or two columns:
 *
 *   number    Float64Array; a null is NaN. A slice holds a missing number as
 *             null, and canonical_cell reads NaN as null, so nothing is lost.
 *   boolean   Float64Array of 0 / 1; a null is NaN.
 *   string    Int32Array of codes into dict[name]; a null is -1. The
 *   datetime  dictionary is sorted by code point, so comparing two codes is
 *             comparing the two strings, which makes grouping, sorting, min
 *             and max on a string column integer work. A datetime is held as
 *             the ISO-8601 text pandas' Timestamp.isoformat() writes, the
 *             same spelling the fingerprint's cell rule gives it.
 *
 * A slice is flat, so pages are read here rather than through hyparquet's
 * readColumn: its Dremel assembly (built for nested lists) and its per-row
 * dictionary lookup are most of the decode time on a flat column, and a
 * dictionary-encoded string column can map dictionary indices to codes
 * without ever building a string per row.
 */

import { parquetMetadata, parquetSchema } from "hyparquet/src/metadata.js";
import { parquetHeader } from "hyparquet/src/column.js";
import { DEFAULT_PARSERS, convert } from "hyparquet/src/convert.js";
import { decompressPage, readDataPage, readDataPageV2 } from "hyparquet/src/datapage.js";
import { readPlain } from "hyparquet/src/plain.js";

/* Code point order for two strings. JavaScript's < compares UTF-16 code
 * units, which puts a character past the BMP (a surrogate pair, 0xD800-0xDFFF)
 * below one in 0xE000-0xFFFF; DuckDB and Python order by code point. Lifting
 * the surrogates above the rest of the BMP on the first difference gives code
 * point order without decoding either string. */
export function cmpStr(a, b) {
  if (a === b) return 0;
  const n = a.length < b.length ? a.length : b.length;
  for (let i = 0; i < n; i++) {
    let x = a.charCodeAt(i), y = b.charCodeAt(i);
    if (x !== y) {
      if (x >= 0xD800) x += x <= 0xDFFF ? 0x2000 : -0x800;
      if (y >= 0xD800) y += y <= 0xDFFF ? 0x2000 : -0x800;
      return x - y;
    }
  }
  return a.length - b.length;
}

function pad(n, width) {
  let s = String(n);
  while (s.length < width) s = "0" + s;
  return s;
}

/* Nanoseconds since the epoch as pandas' Timestamp.isoformat() writes them:
 * no fraction when it is zero, six digits when it is whole microseconds, nine
 * otherwise. Date only carries milliseconds, so the fraction comes from the
 * integer, never from the Date. */
function isoFromNanos(nanos) {
  let secs = nanos / 1000000000n;
  let frac = nanos % 1000000000n;
  if (frac < 0n) { frac += 1000000000n; secs -= 1n; }
  const base = new Date(Number(secs) * 1000).toISOString().slice(0, 19);
  if (frac === 0n) return base;
  if (frac % 1000n === 0n) return base + "." + pad(frac / 1000n, 6);
  return base + "." + pad(frac, 9);
}

const PARSERS = {
  ...DEFAULT_PARSERS,
  timestampFromMilliseconds: (v) => isoFromNanos(BigInt(v) * 1000000n),
  timestampFromMicroseconds: (v) => isoFromNanos(BigInt(v) * 1000n),
  timestampFromNanoseconds: (v) => isoFromNanos(BigInt(v)),
  dateFromDays: (v) => isoFromNanos(BigInt(v) * 86400000000000n),
};

/* The slice type of one schema leaf, or a refusal naming the column. */
function kindOf(name, element) {
  const { type, converted_type: ctype, logical_type: ltype } = element;
  if (ltype && ltype.type === "TIMESTAMP" && ltype.isAdjustedToUTC) {
    throw new Error(`slice column '${name}' is a timezone-aware timestamp; ` +
                    "a slice carries naive datetimes only");
  }
  if (ctype === "DATE" || ctype === "TIMESTAMP_MILLIS" || ctype === "TIMESTAMP_MICROS" ||
      (ltype && ltype.type === "TIMESTAMP") || (!ctype && type === "INT96")) return "datetime";
  if (type === "BOOLEAN") return "boolean";
  if (ctype === "DECIMAL") return "number";
  if (type === "BYTE_ARRAY" && (ctype === "UTF8" || (ltype && ltype.type === "STRING") ||
                                (!ctype && !ltype))) return "string";
  if ((type === "INT32" || type === "INT64" || type === "FLOAT" || type === "DOUBLE") &&
      (!ctype || /^U?INT_/.test(ctype)) &&
      (!ltype || ltype.type === "INTEGER")) return "number";
  throw new Error(`slice column '${name}' has Parquet type ${type}` +
                  (ctype ? `/${ctype}` : "") + "; a slice carries numbers, booleans, " +
                  "strings and naive datetimes only");
}

/* One column being filled: numbers straight into a Float64Array, strings as
 * provisional codes in first-seen order (sorted and remapped at the end). */
function sink(kind, rows) {
  if (kind === "number" || kind === "boolean") return { kind, out: new Float64Array(rows) };
  return { kind, out: new Int32Array(rows), seen: new Map(), words: [] };
}

function wordCode(s, v) {
  let c = s.seen.get(v);
  if (c === undefined) { c = s.words.length; s.seen.set(v, c); s.words.push(v); }
  return c;
}

/* Values a page decoded (or a dictionary holds) as what the sink stores. */
function encodeValues(s, values) {
  const n = values.length;
  const out = s.out instanceof Float64Array ? new Float64Array(n) : new Int32Array(n);
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null || v === undefined) out[i] = s.out instanceof Float64Array ? NaN : -1;
    else out[i] = s.out instanceof Float64Array ? Number(v) : wordCode(s, v);
  }
  return out;
}

/* Every page of one column chunk into the sink, from row *at* on. */
function readChunk(reader, rows, decoder, s, at) {
  const maxDef = decoder.element.repetition_type === "REQUIRED" ? 0 : 1;
  const nullValue = s.out instanceof Float64Array ? NaN : -1;
  let dict = null;
  let row = 0;
  while (row < rows && reader.offset < reader.view.byteLength - 1) {
    const header = parquetHeader(reader);
    const bytes = new Uint8Array(reader.view.buffer, reader.view.byteOffset + reader.offset,
                                 header.compressed_page_size);
    reader.offset += header.compressed_page_size;
    const size = Number(header.uncompressed_page_size);
    if (header.type === "DICTIONARY_PAGE") {
      const page = decompressPage(bytes, size, decoder.codec, undefined);
      const plain = readPlain({ view: new DataView(page.buffer, page.byteOffset, page.byteLength),
                                offset: 0 },
                              decoder.type, header.dictionary_page_header.num_values,
                              decoder.element.type_length);
      dict = encodeValues(s, convert(plain, decoder));
      continue;
    }
    let decoded, encoding;
    if (header.type === "DATA_PAGE") {
      decoded = readDataPage(decompressPage(bytes, size, decoder.codec, undefined),
                             header.data_page_header, decoder);
      encoding = header.data_page_header.encoding;
    } else if (header.type === "DATA_PAGE_V2") {
      decoded = readDataPageV2(bytes, header, decoder);
      encoding = header.data_page_header_v2.encoding;
    } else {
      continue;  // an index page carries no values
    }
    const { definitionLevels: defs, dataPage } = decoded;
    const values = dict && encoding.endsWith("_DICTIONARY") ? dataPage
      : encodeValues(s, convert(dataPage, decoder));
    const lookup = dict && values === dataPage ? dict : null;
    const count = defs && defs.length ? defs.length : values.length;
    const out = s.out;
    let v = 0;
    for (let k = 0; k < count; k++, row++) {
      if (maxDef && defs && defs.length && defs[k] < maxDef) { out[at + row] = nullValue; continue; }
      const x = values[v++];
      out[at + row] = lookup ? lookup[x] : x;
    }
  }
  if (row !== rows) throw new Error(`slice column '${decoder.pathInSchema[0]}' decoded ${row} of ${rows} rows`);
}

/* A string sink's dictionary sorted by code point, its codes remapped. */
function finish(s) {
  if (!s.words) return { data: s.out };
  const order = s.words.map((_, i) => i).sort((a, b) => cmpStr(s.words[a], s.words[b]));
  const remap = new Int32Array(s.words.length);
  const dict = new Array(s.words.length);
  for (let r = 0; r < order.length; r++) { remap[order[r]] = r; dict[r] = s.words[order[r]]; }
  const codes = s.out;
  for (let i = 0; i < codes.length; i++) if (codes[i] >= 0) codes[i] = remap[codes[i]];
  return { data: codes, dict };
}

/**
 * Decode one Parquet block into the engine's columnar table.
 *
 * @param {Uint8Array|ArrayBuffer} bytes the block's raw Parquet bytes (already
 *   base64-decoded, and gunzipped if the carrier gzipped them)
 * @returns {{columns: Array<{name: string, type: string, integer?: boolean}>, rows: number,
 *   data: Object<string, Float64Array|Int32Array>, dict: Object<string, string[]>}}
 */
export function decodeParquet(bytes) {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (u8.length > 2 && u8[0] === 0x1f && u8[1] === 0x8b) {
    throw new Error("the block is still gzipped; gunzip it before load()");
  }
  const metadata = parquetMetadata(u8, { parsers: PARSERS, geoparquet: false });
  const tree = parquetSchema(metadata);
  const rows = metadata.row_groups.reduce((n, g) => n + Number(g.num_rows), 0);
  const columns = [];
  const sinks = {};
  const leaves = {};
  for (const leaf of tree.children) {
    const name = leaf.element.name;
    if (leaf.children.length || leaf.element.repetition_type === "REPEATED") {
      throw new Error(`slice column '${name}' is nested; a slice is flat`);
    }
    const kind = kindOf(name, leaf.element);
    const col = { name, type: kind };
    /* Whole numbers stored as integers: the runtime spells a stamped block's
     * cells as pandas' CSV does, where 1 and 1.0 differ. */
    if (kind === "number" && leaf.element.converted_type !== "DECIMAL" &&
        (leaf.element.type === "INT32" || leaf.element.type === "INT64")) col.integer = true;
    columns.push(col);
    sinks[name] = sink(kind, rows);
    leaves[name] = leaf;
  }
  const view = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
  let at = 0;
  for (const group of metadata.row_groups) {
    const groupRows = Number(group.num_rows);
    for (const chunk of group.columns) {
      const meta = chunk.meta_data;
      if (chunk.file_path || !meta) throw new Error("a slice block must be one self-contained file");
      const name = meta.path_in_schema[0];
      const leaf = leaves[name];
      const start = Number(meta.dictionary_page_offset || meta.data_page_offset);
      const reader = {
        view: new DataView(view.buffer, view.byteOffset + start, Number(meta.total_compressed_size)),
        offset: 0,
      };
      const decoder = {
        pathInSchema: meta.path_in_schema,
        element: leaf.element,
        schemaPath: [tree, leaf],
        ...meta,
        parsers: PARSERS,
      };
      readChunk(reader, groupRows, decoder, sinks[name], at);
    }
    at += groupRows;
  }
  const data = {};
  const dict = {};
  for (const col of columns) {
    const done = finish(sinks[col.name]);
    data[col.name] = done.data;
    if (done.dict) dict[col.name] = done.dict;
  }
  return { columns, rows, data, dict };
}
