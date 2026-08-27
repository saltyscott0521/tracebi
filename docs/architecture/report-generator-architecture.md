# Report Generator — Architecture (locked)

> **⚠️ Superseded by [report-architecture-v2.md](report-architecture-v2.md)** —
> the one-lane reshape (shipped 2026-08-16). This document describes the earlier
> **two-lane** build (a governed spec lane *and* a freeform package lane). The
> reshape collapsed them: a report is now a single artifact package under
> `reports/`, and a JSON spec is one serialization that compiles into the same
> artifact, not a separate lane. Kept as the historical record of the two-lane
> build; its still-true kernel (the safe embedder, the CSP, the receipt
> semantics of §4, and the ECharts layer of §6) survived verbatim into the code
> and is restated in v2 §1. Read v2 for the current architecture; read this for
> why the kernel is shaped the way it is.

Status (at the time): **shipped.** Product and architecture were nailed down with
the maintainer, then pressure-tested against the code by a five-lens design review
(17 findings, 4 blocking — all resolved below, none papered over). The build plan
in §8 (M0–M4) was complete: the trust kernel, template packages, the `report.py`
escape hatch, and the ECharts chart layer, all in `tracebi/reports/` with tests,
and `dashboards/` folded into `reports/`.

---

## 1. Product

The report generator is a **build step**. It takes a report definition plus live
model data and emits **one self-contained `.html`** — CSS in `<style>`, JS in
`<script>`, the model's data embedded as JSON — plus a `.manifest.json` receipt.
The `.html` is portable: open it offline, email it, archive it.

It is differentiated because it is **self-contained AND provable**: the numbers the
page is built on are embedded, fingerprinted, and recorded, so a reviewer with the
file alone can confirm — offline, no model access — that the data it ships is
exactly what the recorded queries produced. The presentation (CSS/JS) is free and
unvalidated by design; **the receipt covers the numbers, not the pixels** (§4).

---

## 2. Architecture — one kernel, two lanes, one output

```
   (A) GOVERNED SPEC   reports/*.json            (B) FREEFORM PACKAGE   reports/<name>/
       built-in renderers draw the page              report.json (queries) + report.py?
                 │                                    template.html · style.css · script.js
                 └───────────────┬─────────────────────────┘
                                 ▼
        ┌─────────────────── SHARED KERNEL ───────────────────┐
        │ 1  resolve + stamp   ds = model.execute(query)       │
        │                      → last lineage node stamps      │
        │                        {model, query_spec}; fingerprint
        │ 2  embed             canonical bytes + display JSON,  │
        │                      via the safe encoder (§5)        │
        │ 3  receipt           manifest-first; fingerprints all │
        │                      data-bearing sections            │
        │ 4  inline            one file: CSS + JS + ECharts +   │
        │                      embedded data                    │
        └───────────────────────────┬──────────────────────────┘
                                     ▼
             report.html   +   report.html.manifest.json
             self-contained · offline · portable · checkable
```

The two lanes differ only in **who draws the page** — the built-in renderers (from a
spec) or the analyst's own `template.html` (a freeform package). Both run through
the same data + receipt kernel and emit the same two artifacts.

### Reuse vs new (the honest map)

Almost every kernel *primitive* already exists:

| Kernel step | Reuse | New |
|---|---|---|
| resolve + stamp | `DataRef`/`QuerySpec` validation; `model.execute()` stamps query+model+input fingerprints | resolver glue (~40 lines) |
| fingerprint | `frame_fingerprint` (`dataset.py:18-35`) | — |
| receipt | `to_manifest_dict` fingerprints any DataSet section incl. custom types; `build_manifest`; manifest-first ordering | an `embedded_data` block on the manifest |
| inline one file | `render_shell` string-inlining; `template`/`head_extra`/`body_extra`/`template_context` seams; `HTMLRenderer.serve` | the **safe JSON embedder**; the **template-package loader** |
| discovery | `_register_spec_file` factory pattern; registry name+factory contract | `_register_template_package(dir)` branch |
| CLI | the scaffold + subcommand plumbing (`cmd_new_model` et al.) | `tracebi new-report`, `tracebi report build/preview`, `tracebi verify --file` |
| verify (model reproduction) | `verify_manifest` — **zero changes** | a **separate** offline file checker |

Net: the new code is small — a safe embedder, a thin template-package renderer, a
discovery branch, an offline checker, and CLI. The one genuinely new *primitive* is
the canonical-bytes data embed.

---

## 3. What the pressure test caught (blocking, resolved)

1. **A tampered file still passed `verify`.** Editing a shipped report's grand total
   to `$99,999,999` left `tracebi verify` returning REPRODUCES / exit 0 — it re-runs
   queries against the model and never opens the file.
   **Fix:** a separate offline checker, `tracebi verify --file report.html`, that
   extracts the embedded data and rehashes it against the manifest. Runs by default
   when the `.html` sits next to its manifest.

2. **The "reviewer can re-check the numbers" claim was broken.** Embedding data as
   JSON records and re-fingerprinting does *not* match the stored fingerprint —
   floats truncate, dtypes are lost, CSV reserialization drifts by 1 ULP.
   **Fix:** embed the *exact bytes the fingerprint was taken over* — `repr(columns)`,
   `repr(dtypes)`, and `df.to_csv(index=False)` verbatim. The checker hashes the
   recovered strings **without rebuilding a DataFrame**. Proven to match exactly.
   Do **not** introduce a second fingerprint algorithm — `frame_fingerprint` stays
   the single algorithm across `verify`, manifests, and `DataModel.load`.

3. **Embedded data was a stored-XSS vector.** Model data carries
   attacker-influencable strings (issuer names parsed from prose blobs). A cell
   containing `</script><img onerror=…>` naively embedded breaks out and executes in
   a file the recipient opens offline.
   **Fix:** the safe encoder in §5.

4. **The receipt covers the data — not the pixels.** The fingerprint covers the
   embedded JSON, never the rendered DOM. The page's JS can round, rescale, hardcode
   a figure, or run a wrong client-side sum, all invisible to the receipt.
   **Handle:** state it plainly (§4); flag `report.py`-computed data as unverifiable;
   ship a lint that flags hardcoded numbers — a nudge, never a proof.

---

## 4. What the receipt proves — and what it doesn't

Ships in the docs **and** in `verify` output.

**Proven**
- These queries against these models produced data with these fingerprints, at render time.
- Re-running the queries reproduces them — `tracebi verify manifest.json`.
- The bytes shipped in *this file* are exactly those fingerprinted bytes — `tracebi verify --file`.

**Not proven**
- **Embedded → displayed.** The JS can show a number that isn't in the stamped data.
  The receipt covers the blob, not the render.
- **`report.py` outputs.** Arbitrary Python is unverifiable-by-replay; its *inputs*
  are stamped, its *output* is not re-run — and must never read as green
  (verdict `unverifiable`, but surfaced as a coverage line, not a silent exit 0).

> Verified: the data in this file came from these queries and reproduces from the
> model. Trusted, not verified: everything the page draws from that data.

Two verify checks, kept distinct: `verify manifest.json` (query → model) and
`verify --file report.html` (embedded bytes → manifest). Neither implies the other.

---

## 5. Security posture (the shipped file is emailed and opened by third parties)

**Safe data-embedding contract** — escaping happens in Python before the string
reaches the shell (the custom-template Jinja env is `autoescape=False`; there is no
safe embedder to inherit):

```python
def embed_json(obj, elem_id: str) -> str:
    raw  = json.dumps(obj, ensure_ascii=False, default=str)
    safe = (raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    return f'<script id="{elem_id}" type="application/json">{safe}</script>'
```

`type="application/json"` (non-executable); the client reads via
`JSON.parse(el.textContent)` only; data-derived strings are **never** passed to
`innerHTML` / `insertAdjacentHTML` / `document.write`. Verified to neutralize the
injection payload and round-trip the exact bytes for the §3.2 checker.

**CSP** — a conservative meta as the first child of `<head>`:

```
default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'
```

`connect-src 'none'` kills phone-home (a bundled lib cannot beacon the embedded fund
data). ECharts needs **no `'unsafe-eval'`** — a concrete win of choosing it over
Plotly; `'unsafe-inline'` is unavoidable in a static file, so **CSP is defense in
depth, not the XSS control — the safe embedder is.** A malicious analyst is out of
scope by design.

---

## 6. Charts — ECharts, pluggable

The whole product renders charts **client-side** from the embedded data. This fits
the kernel: a chart is just the stamped JSON handed to a library in the browser. The
Python side stays light (it emits data + config; the browser draws), preserving the
earlier no-matplotlib decision.

- **Library: Apache ECharts, default, pluggable.** No `eval` (clean CSP), canvas
  performance for fund-scale data, tree-shakeable so the inlined bundle carries only
  the chart types a report uses. A freeform package may inline a different library.
- **Governed lane:** `ChartSection`'s config (`chart_type`, `x`, `y`, `color`…)
  compiles to an ECharts `option` object + a small init script.
- **Freeform lane:** the analyst's `script.js` calls ECharts directly on the embedded
  data.
- **The bundle is inlined** (offline, no CDN — enforced by `connect-src 'none'`).
- **PDF stays lib-agnostic.** WeasyPrint runs no JS, so client-side charts can't
  render in a PDF. The existing server-side SVG renderer (`chart.py`,
  `ChartSpec.to_svg`) is **kept for the print path only**: one `ChartSection` config
  → two renderers (ECharts for interactive HTML, SVG for PDF). No new dependency, no
  kaleido, no headless browser.

---

## 7. Coexistence — one `reports/`

A file is a spec or a factory; a **directory containing `report.json` + `template.html`**
is a freeform package. All three authoring forms live under `reports/`, with one CLI
noun (`tracebi report build/preview`) an analyst learns regardless of form.

| Form | Location | Who draws | Discovery |
|---|---|---|---|
| Code factory | `reports/*.py` | `@register.report` → `Report` | existing `.py` branch |
| Governed spec | `reports/*.json` | built-in section renderers | existing `_register_spec_file` |
| Freeform package | `reports/<name>/` (a directory) | the analyst's `template.html` | **new** `_register_template_package` |

`dashboards/` has folded into `reports/` (one location): the demo
`portfolio_dashboard.json` now lives in the reference project's `reports/`
(`examples/portfolio_project/`), and the
`TRACEBI_DASHBOARDS_DIR` discovery branch is gone.

---

## 8. Build plan

_All five milestones below have shipped; this section is kept as the record of how
the work was staged and what each milestone proved._

**M0 — kernel primitives (proves the trust story first).** The safe embedder + the
stamped-data helper (canonical bytes), and `tracebi verify --file`. Proof gate:
build one hand-wired package, tamper a number in the `.html`, confirm `verify --file`
fails while `verify manifest.json` still passes — closing §3.1.

**M1 — template-package renderer.** Thin orchestration over `HTMLRenderer`: read
`report.json`, resolve+stamp, build synthetic carrier sections for the receipt, then
**inject the data/style/script blocks by string insertion** before `</head>`/`</body>`
of the rendered HTML — do not depend on the analyst placing `{{ head_extra }}` /
`{{ body_extra }}` (StrictUndefined fails only on *referenced* undefined names, not
*omitted* ones, so a forgotten placeholder silently ships a page with no data).

**M2 — discovery + CLI.** `_register_template_package` branch (subdirectories are
currently skipped); `tracebi new-report`, `tracebi report build/preview`; fold
`dashboards/` into `reports/`.

**M3 — escape hatch + honesty.** The `report.py` `inputs`/`build()` contract; resolve
inputs as stamped DataRefs; fingerprint outputs; set `verifiable=false`; add a
`data_coverage`-style line to `verify` so a Python-derived page never reads as green.

**M4 — chart layer.** `ChartSection` → ECharts `option`; inline the tree-shaken
bundle; keep `ChartSpec.to_svg` for the PDF path. Optional `report lint` for
hardcoded numbers.

**Deliberately not yet:** live callback from the shipped file; live re-render through
the web route (the build step + static serve avoids a new registry seam that would
require converting the tests that rebind `web.api.registry`); any `report.py`
replay-proof (impossible for arbitrary Python); a new fingerprint algorithm.

---

## 9. Decisions (all locked)

| # | Decision | Call |
|---|---|---|
| 1 | Data binding | declarative model queries by default; `report.py` escape hatch (inputs stamped, output not replay-proved) |
| 2 | Portability | static embedded stamped data; client-side render; no live callback |
| 3 | Trust boundary | receipt covers the numbers, not the pixels; stated plainly |
| 4 | Chart engine | **ECharts**, default, pluggable; SVG renderer retained for PDF |
| 5 | PDF | static SVG fallback per chart via the existing renderer (no new dep) |
| 6 | Folders | one `reports/`; a file is a spec, a directory is a package |
| 7 | Self-verifying file | also embed the manifest into the `.html`; still write the loose manifest |
| 8 | Unverifiable surfacing | manifest flag + coverage line; exit 0 stays for hand-authored pages, but green never reads as "verified" |

The worked example (AltsVault API output → phase-① transform → model → report) drives
the first real package once M0–M2 land.
