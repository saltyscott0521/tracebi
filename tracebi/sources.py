"""What feeds the warehouse, and what the warehouse holds: the app's Sources
and Warehouse pages, read from the project's own files.

Upstream of the sink nothing is traced (phase ① is unconstrained), so who
reads what is read from the transform files as text, the same way a person
skimming them would:

- a SQL transform's ``-- source: <connection>.<table>`` header lines, through
  the runner's own parser (:func:`tracebi.transforms.source_directives`);
- ``load_source("<connection>.<table>")`` in a Python or notebook transform;
- a literal path into ``inputs/``: ``'inputs/holdings.csv'`` (SQL's
  ``read_csv``, a fallback, a docstring), or ``"inputs", "holdings.csv"`` as
  ``os.path.join`` and ``pathlib`` spell it.

The limits are those of reading text: a path built from a variable, a glob or
a folder other than ``inputs/`` is not seen, and a file the transform names
only in a comment is counted as read. The answer is a pointer for a person,
never a claim the trust machinery leans on.

Downstream, the warehouse's tables, who wrote each (the certificate the sink
contract recorded) and which models read them, come from what exists: the
warehouse itself, its certificate, and the registered models.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def is_framework_table(name: str) -> bool:
    """A table TraceBi itself owns: the state store's ``tracebi_*`` tables
    (runs, sessions, OAuth tokens, code requests) and Alembic's
    ``alembic_version``. Every place that lists or reads a source's tables
    leaves these out, whatever the connection points at: a connection aimed
    at the state store (a plausible "show me my runs") must not become a
    browser for sessions and tokens."""
    return name.lower().startswith("tracebi_") or name.lower() == "alembic_version"

_INPUT_PATH = re.compile(r"\binputs/([\w.\-/]*\w\.\w+)")
_INPUT_JOIN = re.compile(r"""["']inputs["']\s*[,/]\s*["']([^"'\s]+)["']""")
_LOAD_SOURCE = re.compile(r"""load_source\(\s*["']([A-Za-z_]\w*)\.([A-Za-z_]\w*)["']""")
_CREDENTIAL = re.compile(r"://([^:/@\s]+):[^@\s]+@")
_CONTRACT_NAME = re.compile(r"""\bcontract\(\s*["']([^"'\s]+)["']""")


def inputs_dir() -> Path:
    """The project's ``inputs/`` folder: beside ``transforms/``."""
    from tracebi.transforms import transforms_dir

    return transforms_dir().parent / "inputs"


def _input_files() -> dict[str, Path]:
    """Every file under ``inputs/``, by its project-relative path
    (``inputs/holdings.csv``); hidden files and caches left out."""
    root = inputs_dir()
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "__")))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            found["inputs/" + path.relative_to(root).as_posix()] = path
    return found


def transform_reads() -> dict[str, dict]:
    """``{transform: {"connections": [{connection, table}], "inputs": [path]}}``
    for every transform file, read as text (see the module's note on what
    that can and cannot see). An input is listed only when the file exists."""
    from tracebi.transforms import FORMS, TransformError, source_directives, transforms_dir

    tdir = transforms_dir()
    if not tdir.is_dir():
        return {}
    existing = _input_files()
    out: dict[str, dict] = {}
    for path in sorted(tdir.iterdir()):
        if path.suffix not in FORMS or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        connections: list[dict] = []
        if path.suffix == ".sql":
            try:
                connections = [{"connection": d["connection"], "table": d["table"]}
                               for d in source_directives(text, path.name)]
            except TransformError:
                connections = []   # a header the runner refuses reads nothing
        for m in _LOAD_SOURCE.finditer(text):
            ref = {"connection": m.group(1), "table": m.group(2)}
            if ref not in connections:
                connections.append(ref)
        named = {"inputs/" + p for p in _INPUT_PATH.findall(text)}
        named |= {"inputs/" + p for p in _INPUT_JOIN.findall(text)}
        out[path.stem] = {"connections": connections,
                          "inputs": sorted(p for p in named if p in existing)}
    return out


def read_by(name: str, used_by: list[str], reads: dict[str, dict], runners: list) -> dict:
    """Who reads connector *name*: the transforms whose files name one of its
    tables (with the tables), the medallion layers whose source it is, and the
    models that read it directly (*used_by*). *runners* are ``(pipeline,
    runner)`` pairs."""
    transforms = []
    for transform, r in reads.items():
        tables = [c["table"] for c in r["connections"] if c["connection"] == name]
        if tables:
            transforms.append({"name": transform, "tables": tables})
    layers = [{"pipeline": pipeline, "layer": layer["name"]}
              for pipeline, runner in runners
              for layer in (runner.layers() if hasattr(runner, "layers") else [])
              if layer.get("source") == name]
    return {"transforms": transforms, "layers": layers, "models": list(used_by)}


def inputs_listing() -> dict:
    """The ``inputs/`` folder as the Sources page lists it: each file with its
    size, when it last changed, and the transforms that name it."""
    reads = transform_reads()
    files = []
    for shown, path in _input_files().items():
        stat = path.stat()
        files.append({
            "path": shown,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "read_by": [t for t, r in reads.items() if shown in r["inputs"]],
        })
    return {"folder": "inputs", "exists": inputs_dir().is_dir(), "files": files}


def _reason(exc: BaseException) -> str:
    """One line a page can show for a source it could not reach: the first
    line of the error, any credential in a URL masked."""
    first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    return _CREDENTIAL.sub(r"://\1:***@", first)[:300]


def sql_row_estimates(conn) -> dict[str, int]:
    """``{table: rows}`` from the catalog's own estimate for the tables of the
    connection's current schema, where the database keeps one: Postgres
    ``pg_class.reltuples``, which ANALYZE and autovacuum maintain (a table
    never analysed reads -1 there and is left out). Any other dialect answers
    ``{}``. A ``count(*)`` per table is the slow query on a large database,
    so a listing never runs one. *conn* is a SQLAlchemy connection."""
    if conn.dialect.name != "postgresql":
        return {}
    from sqlalchemy import text

    rows = conn.execute(text(
        "SELECT c.relname, c.reltuples FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')")).fetchall()
    return {str(name): int(n) for name, n in rows if n is not None and n >= 0}


def connection_tables(connector) -> dict:
    """What *connector* holds, read now: ``{connected: true, tables: [{name,
    columns: [{name, type}], rows, rows_exact}]}``, or ``{connected: false,
    reason, variable?}`` when it cannot be reached here (its ``${VAR}`` unset,
    the database refusing). Read-only and from metadata; a DuckDB file is
    opened read-only and closed, and a database connection is released before
    this returns, so nothing is held for the next request. ``rows`` is exact
    where counting is cheap (a DuckDB file, frames held in memory), the
    catalog's estimate with ``rows_exact: false`` for a SQL database that
    keeps one (:func:`sql_row_estimates`), else None: no table is counted
    row by row here. Framework tables are left out and counted in
    ``hidden_framework_tables``."""
    from tracebi.connections import ConnectionConfigError
    from tracebi.connectors.memory_connector import MemoryConnector
    from tracebi.connectors.sql_connector import SQLConnector

    d = connector.describe()
    try:
        if d.get("type") == "DuckDBConnector" and d.get("database") not in (None, ":memory:"):
            from tracebi.warehouse import as_warehouse
            from tracebi.workbench import _warehouse_tables

            wh = getattr(connector, "warehouse", None)
            target = wh.sink if wh is not None else str(d["database"])
            if not as_warehouse(target).exists():
                return {"connected": False, "reason": "Nothing is built here yet."}
            hidden: list[str] = []
            return {"connected": True, "tables": [
                {"name": t["name"], "rows": t["rows"], "rows_exact": True,
                 "columns": [{"name": c, "type": ty} for c, ty in t["columns"].items()]}
                for t in _warehouse_tables(target, profile=False, hidden=hidden)],
                "hidden_framework_tables": len(hidden)}
        names = connector.list_tables()
        if names is None:
            return {"connected": True, "tables": None,
                    "reason": "This kind of source cannot list its tables."}
        estimates: dict[str, int] = {}
        if isinstance(connector, SQLConnector):
            with connector._engine.connect() as conn:   # list_tables() connected it
                estimates = sql_row_estimates(conn)
        shown = sorted(n for n in names if not is_framework_table(n))
        tables = []
        for table in shown:
            cols = connector.column_schema(table) or []
            if isinstance(connector, MemoryConnector):
                rows, exact = len(connector.load(table)), True
            else:
                rows, exact = estimates.get(table), False
            tables.append({"name": table, "rows": rows, "rows_exact": exact,
                           "columns": [{"name": c["name"], "type": c["dtype"]} for c in cols]})
        return {"connected": True, "tables": tables,
                "hidden_framework_tables": len(names) - len(shown)}
    except ConnectionConfigError as exc:
        if exc.variable:
            return {"connected": False, "variable": exc.variable,
                    "reason": f"{exc.variable} is not set"}
        return {"connected": False, "reason": _reason(exc)}
    except Exception as exc:  # noqa: BLE001 — an unreachable source is an answer
        return {"connected": False, "reason": _reason(exc)}
    finally:
        if isinstance(connector, SQLConnector):
            connector.disconnect()


def _contract_owners() -> dict[str, str]:
    """Certificate record name → the transform file that writes it: the
    ``name`` in a ``<transform>.contract.yaml``, the first argument of a
    ``with contract("...")`` block in a Python transform, and each
    transform's own file name. A contract file wins over a Python block of
    the same name (the pandas twin of a SQL transform declares the same
    record; the SQL one is what its pipeline runs)."""
    from tracebi.contracts import read_contract_file
    from tracebi.transforms import FORMS, contract_file, transforms_dir

    owners: dict[str, str] = {}
    tdir = transforms_dir()
    if not tdir.is_dir():
        return owners
    files = [p for p in sorted(tdir.iterdir()) if p.suffix in FORMS and p.is_file()]
    for path in files:
        owners.setdefault(path.stem, path.stem)
    for path in files:
        if path.suffix == ".sql":
            continue
        try:
            for name in _CONTRACT_NAME.findall(path.read_text(encoding="utf-8")):
                owners.setdefault(name, path.stem)
        except (OSError, UnicodeDecodeError):
            continue
    for path in files:
        beside = contract_file(path)
        if beside is None:
            continue
        try:
            owners[read_contract_file(beside, path.stem)["name"]] = path.stem
        except Exception:  # noqa: BLE001 — a broken contract file names nothing
            continue
    return owners


def contract_files() -> dict[str, str]:
    """Certificate record name → the file its checks are declared in, as the
    project names it: the ``<transform>.contract.yaml`` beside the transform
    that writes it, else the transform itself (a ``with contract(...)``
    block). The record's own name can differ from both ("holdings" in
    ``holdings_transform.contract.yaml``), so a reader is shown the file."""
    from tracebi.transforms import contract_file, find_transform

    files: dict[str, str] = {}
    for record, transform in _contract_owners().items():
        try:
            path = find_transform(transform)
        except Exception:  # noqa: BLE001 — two forms of one name: no single file
            continue
        if path is not None:
            files[record] = (contract_file(path) or path).as_posix()
    return files


def is_warehouse(entry: dict) -> bool:
    """A connector-list entry that is a warehouse: DuckDB on a file, or the
    project's warehouse on any tier."""
    return entry.get("type") == "DuckDBConnector" and entry.get("database") not in (None, ":memory:")


def warehouses(registry) -> list[dict]:
    """Every warehouse the project's connectors name, each with its tier,
    where it is, its size, the DuckDB version its certificate records, the
    models that read it, and every table in it: its kind (``table``, or
    ``view`` with the ``bases`` the certificate recorded), rows, column count,
    who wrote it (the transform named by the certificate, and when), which
    models read it and its sink-contract status. ``writers`` is each transform whose
    certificate covers tables here, once: its contract file and note, its
    tables, and what its run read from outside the warehouse (``read``). The
    certificate records what a run read, not what each table came from, so
    that is said of the run, never of a table. Read-only; per-column
    profiles are left to the table page."""
    from tracebi.contracts import read_contracts
    from tracebi.workbench import warehouse_view

    owners = _contract_owners()
    tables_of: dict[str, dict[str, list[str]]] = {}   # connector → table → models
    for info in registry.list_models():
        model = registry.get_model(info["name"])
        if model is None:
            continue
        for t in model.info().get("tables", []):
            readers = tables_of.setdefault(t["connector"], {}).setdefault(t["source"], [])
            if model.name not in readers:
                readers.append(model.name)

    out = []
    for entry in registry.list_connectors():
        if not is_warehouse(entry):
            continue
        connector = registry.get_connector(entry["name"])
        wh = getattr(connector, "warehouse", None)
        target = wh.sink if wh is not None else str(entry["database"])
        view = warehouse_view(target, profile=False)
        certs = ((read_contracts(target) or {}).get("transforms") or {}) if view["exists"] else {}
        latest = max(certs.values(), key=lambda r: r.get("checked_at") or "", default={})
        storage = entry.get("storage") or {}
        readers = tables_of.get(entry["name"], {})
        tables = [_table_entry(t, readers, owners, certs) for t in view["tables"]]
        section: dict[str, Any] = {
            "name": entry["name"],
            "tier": getattr(connector, "tier", "file"),
            "where": storage.get("where"),
            "exists": view["exists"],
            "size": storage.get("size"),
            "engine_version": latest.get("engine_version"),
            "read_by": entry.get("used_by", []),
            "tables": tables,
            "writers": _writers(tables, certs, owners),
            "hidden_framework_tables": view.get("hidden_framework_tables", 0),
        }
        if view.get("error"):
            section["error"] = view["error"]
        out.append(section)
    return out


def _table_entry(t: dict, readers: dict[str, list[str]], owners: dict[str, str],
                 certs: Optional[dict] = None) -> dict:
    from tracebi.contracts import view_record

    contract = t.get("contract") or {"status": "no_contract"}
    record = contract.get("transform")
    # A sink view: the certificate names the transform that defined it and
    # the tables it reads, whether or not a check touches it.
    defined = view_record({"transforms": certs or {}}, t["name"]) if t.get("kind") == "view" else None
    at = contract.get("checked_at")
    if not record and defined:
        record, at = defined["contract"], defined["checked_at"]
    written_by: Optional[dict] = None
    if record:
        written_by = {"transform": owners.get(record), "contract": record, "at": at}
    extra = {"bases": defined["bases"]} if defined else {}
    return {
        "name": t["name"],
        "kind": t.get("kind", "table"),
        **extra,
        "rows": t["rows"],
        "columns": len(t["columns"]),
        "written_by": written_by,
        "read_by": readers.get(t["name"], []),
        "contract": {k: contract.get(k) for k in ("status", "checks", "checked_at") if k in contract},
    }


def _writers(tables: list[dict], certs: dict, owners: dict[str, str]) -> list[dict]:
    """Each certificate record that wrote tables here, in the order its first
    table is listed: the transform, when, the file declaring its checks, its
    note, its tables, and the outside inputs its run read (a connection with
    its fingerprint and how it was read, or the committed snapshot that
    stood in)."""
    files = contract_files() if tables and any(t["written_by"] for t in tables) else {}
    out: dict[str, dict] = {}
    for t in tables:
        record = (t["written_by"] or {}).get("contract")
        if not record:
            continue
        if record not in out:
            rec = certs.get(record) or {}
            out[record] = {
                "contract": record,
                "transform": owners.get(record),
                "at": rec.get("checked_at"),
                "file": files.get(record),
                "note": rec.get("note"),
                "checks": len(rec.get("checks") or []),
                "tables": [],
                "read": [{
                    "ref": ref, "connection": src.get("connection"), "table": src.get("table"),
                    "fingerprint": src.get("fingerprint"), "rows": src.get("rows"),
                    "loaded_at": src.get("loaded_at"),
                    # How the run read it (scanner | arrow), when the certificate
                    # says; a table read through the connector records none.
                    "method": src.get("method"),
                    # The committed snapshot stood in for the connection on that run.
                    "snapshot": src.get("fallback") if src.get("source_fallback") else None,
                } for ref, src in (rec.get("sources") or {}).items()],
            }
        out[record]["tables"].append(t["name"])
    return list(out.values())


def transforms_listing(registry) -> list[dict]:
    """Every transform file in ``transforms/``, as Data's Transforms tab lists
    it: its form, the file declaring its checks (the ``.contract.yaml`` beside
    it, or the file itself when it holds a ``with contract(...)`` block) and
    the note they carry, the pipelines that run it and the models they
    refresh, and what a certificate says it wrote: the tables, the models
    that read them, and when. A transform no certificate names (one that has
    not run here, or the pandas twin of a SQL transform) wrote nothing as far
    as anything recorded knows: ``tables`` is empty, ``written_at`` null."""
    from tracebi.contracts import read_contract_file
    from tracebi.transforms import FORMS, contract_file, transform_form, transforms_dir

    tdir = transforms_dir()
    if not tdir.is_dir():
        return []
    files = [p for p in sorted(tdir.iterdir()) if p.suffix in FORMS and p.is_file()]

    runs: dict[str, list[tuple[str, list[str]]]] = {}   # transform → [(pipeline, models)]
    for name in registry.list_pipeline_names():
        runner = registry.get_pipeline(name)
        transform = getattr(runner, "transform", None)
        if not isinstance(transform, str) or not transform:
            continue
        model = getattr(runner, "model", None)
        named = [m for m in (getattr(runner, "models", None) or []) if isinstance(m, str) and m]
        runs.setdefault(transform, []).append(
            (name, named or ([model] if isinstance(model, str) and model else [])))

    wrote: dict[str, dict] = {}   # transform → {tables, models, at, note}
    for w in warehouses(registry):
        for writer in w["writers"]:
            if not writer["transform"]:
                continue
            entry = wrote.setdefault(writer["transform"], {"tables": [], "models": [], "at": None, "note": None})
            entry["tables"] += writer["tables"]
            entry["note"] = entry["note"] or writer["note"]
            if writer["at"] and (entry["at"] is None or writer["at"] > entry["at"]):
                entry["at"] = writer["at"]
            for t in w["tables"]:
                if t["name"] in writer["tables"]:
                    entry["models"] += [m for m in t["read_by"] if m not in entry["models"]]

    out = []
    for path in files:
        name = path.stem
        written = wrote.get(name, {"tables": [], "models": [], "at": None, "note": None})
        note = written["note"]
        declared = contract_file(path)
        if declared is not None and note is None:
            try:
                note = read_contract_file(declared, name).get("note")
            except Exception:  # noqa: BLE001 — a broken contract file still names its file
                note = None
        elif declared is None and path.suffix != ".sql":
            try:
                declared = path if _CONTRACT_NAME.search(path.read_text(encoding="utf-8")) else None
            except (OSError, UnicodeDecodeError):
                declared = None
        pipelines = runs.get(name, [])
        models = [m for _, ms in pipelines for m in ms] + written["models"]
        out.append({
            "name": name,
            "form": transform_form(path),
            "file": f"{tdir.name}/{path.name}",
            "contract_file": f"{tdir.name}/{declared.name}" if declared is not None else None,
            "note": note,
            "pipelines": [p for p, _ in pipelines],
            "models": list(dict.fromkeys(models)),
            "tables": sorted(set(written["tables"])),
            "written_at": written["at"],
        })
    return out
