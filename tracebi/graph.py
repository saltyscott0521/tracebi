"""The project as one graph: every source, transform, warehouse table, model
and report, what feeds what, and what an agent may read.

Two readers, one picture: the app's map (``GET /api/graph``) and the agent
gateway (``describe_project``) both serve :func:`project_graph`, so the person
approving an agent's work and the agent look at the same thing
(``design/control-tower.md``).

Nothing here is new knowledge. Every node and edge is composed from what the
API already answers, and the edges are exactly the four facts Data's
Overview has drawn since the board (``design/data-flow-board.md``):

- source → transform: a transform's file names the source (``read_by``, read
  from the transform's text by :func:`tracebi.sources.transform_reads`);
- transform → its group in the warehouse: the sink certificate's writers;
- group → model: the models that read the group's tables;
- model → report: the models a report's bindings read.

Edges are facts, never guesses. A *gap* is a node wired on one side only: a
file under ``inputs/`` no transform names, a transform no pipeline runs and no
certificate names, a warehouse table no model reads, a model no report reads.
TraceBi's own tables are never nodes, and nothing in the graph is a
credential's value: a connection set by a variable is named by the variable.

A report's trust is the verdict the desk already computed for its last build
(:func:`tracebi.desk.cached_verdict`). The graph never re-runs a build's
queries: a build no one has re-checked in this process reads "Not checked".
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Optional
from urllib.parse import quote

#: The lanes, left to right in the order the data moves.
SOURCES, TRANSFORMS, WAREHOUSE, MODELS, REPORTS = range(5)

# The mechanism word on a node, as the app's chips say it.
_DIALECT = {
    "postgresql": "Postgres", "sqlite": "SQLite", "mysql": "MySQL", "mariadb": "MariaDB",
    "mssql": "SQL Server", "oracle": "Oracle", "snowflake": "Snowflake",
    "bigquery": "BigQuery", "duckdb": "DuckDB",
}
_TYPE = {
    "BigQueryConnector": "BigQuery", "SnowflakeConnector": "Snowflake",
    "DuckDBConnector": "DuckDB", "CSVConnector": "CSV", "MemoryConnector": "Python",
}
_EXT = {
    "csv": "CSV", "tsv": "TSV", "parquet": "Parquet", "json": "JSON", "xlsx": "Excel",
    "sqlite": "SQLite", "duckdb": "DuckDB",
}
_FORM = {"sql": "SQL", "python": "Python", "notebook": "Notebook"}

# The trust words, as web/ui/src/words.js (checksWords) and the desk's
# verdicts say them. A page prints the text as given and adds the age itself.
_CHECKS = {
    "satisfied": ("ok", "Checks passed"),
    "stale": ("warn", "Changed since checked"),
    "no_contract": ("none", "No checks"),
}
_VERDICT = {
    "reproduces": ("ok", "Reproduces"),
    "source_drift": ("warn", "Drifted"),
    "not_reproduced": ("bad", "Drifted"),
    "error": ("bad", "Error"),
}
_NOT_CHECKED = ("none", "Not checked")
_NOT_A_SINK = {"state": "none", "text": "Not a sink"}
_LOOSE = "(none)"
_CREDENTIAL = re.compile(r"://([^:/@\s]+):[^@\s]+@")


def _seg(text: str) -> str:
    """One path segment, encoded as the app's ``encodeURIComponent`` does."""
    return quote(str(text), safe="-_.!~*'()")


def _segs(path: str) -> str:
    return "/".join(_seg(p) for p in str(path).split("/"))


def _mtime(path: Optional[str]) -> Optional[str]:
    """When *path* last changed, as ISO-8601 UTC, or None."""
    try:
        stamp = os.path.getmtime(path) if path else None
    except OSError:
        return None
    return None if stamp is None else datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _names(ids: list[str]) -> str:
    """``read by a, b`` from node ids, at most three named."""
    names = [i.split(":", 1)[1] for i in ids]
    shown = ", ".join(names[:3])
    return shown + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def _node(id_: str, kind: str, lane: int, *, name: str, label: str, chip: str, sub: str,
          open_: str, origin: str, readers: list[str], writers: list[str], moved: dict,
          trust: dict, agents: dict, parent: Optional[str] = None,
          reach: Optional[dict] = None, gap: Optional[str] = None,
          rows: Any = None) -> dict:
    passport: dict[str, Any] = {
        "origin": origin, "readers": readers, "writers": writers,
        "moved": moved, "trust": trust, "agents": agents,
    }
    if reach is not None:
        passport["reach"] = reach
    node: dict[str, Any] = {
        "id": id_, "kind": kind, "lane": lane, "parent": parent, "label": label,
        "name": name, "chip": chip, "sub": sub, "open": open_, "passport": passport,
        "gap": {"reason": gap} if gap else None,
    }
    # A row count is a number, or absent: never a word standing in for one.
    if isinstance(rows, int) and not isinstance(rows, bool):
        node["rows"] = rows
    return node


def _checks_trust(contracts: list[dict], checks: Optional[int] = None) -> dict:
    """What the sink checks of some tables say, in the locked words: any
    stale table makes them all stale, and only all satisfied is ok."""
    statuses = [(c or {}).get("status") or "no_contract" for c in contracts]
    if "stale" in statuses:
        state, text = _CHECKS["stale"]
    elif statuses and all(s == "satisfied" for s in statuses):
        state, text = _CHECKS["satisfied"]
        if checks:
            text = f"{text} · {_plural(checks, 'check')}"
    elif "satisfied" in statuses:
        # Some tables checked, some not: never green for the unchecked ones.
        n = statuses.count("satisfied")
        state, text = "none", f"{_CHECKS['satisfied'][1]} on {n} of {_plural(len(statuses), 'table')}"
    else:
        state, text = _CHECKS["no_contract"]
    return {"state": state, "text": text}


def _loaded_models() -> dict:
    """The project's models keyed as ``GET /api/desk`` keys them (file stem
    and declared name), so a verdict the desk cached is found here."""
    from tracebi.model_registry import get_model, list_models

    models: dict = {}
    for name in list_models():
        try:
            model = get_model(name)
        except Exception:  # noqa: BLE001 — a broken model leaves its reports unchecked
            continue
        models[name] = model
        if getattr(model, "name", None):
            models[model.name] = model
    return models


def project_graph(registry, *, root: Optional[str] = None) -> dict:
    """The project as ``{summary, nodes, edges}`` (the shape is
    ``docs/reference/api-routes.md``'s ``GET /api/graph``).

    *registry* is the populated registry; *root* the project directory
    (default the working directory), where ``output/`` holds the builds.
    Reports in a folder the caller may not view are left out, with their
    edges, as ``/api/reports`` leaves them out. One pass: the warehouse is
    read once, each reachable connection's tables once."""
    from tracebi.connections import agent_may_read
    from tracebi.desk import cached_verdict
    from tracebi.model_registry import model_path
    from tracebi.sources import connection_tables, transforms_listing, warehouses
    from tracebi.web.api.routers.connectors import list_connectors
    from tracebi.web.api.routers.reports import list_reports
    from tracebi.web.api.routers.sources import list_inputs

    root = os.path.abspath(root or os.getcwd())
    nodes: list[dict] = []
    edges: list[list[str]] = []

    whs = warehouses(registry)
    transforms = transforms_listing(registry, whs)
    by_transform = {t["name"]: t for t in transforms}
    # What each transform's last run read, from the certificate: per
    # connection, whether the committed snapshot stood in.
    run_reads: dict[str, list[dict]] = {}
    for w in whs:
        for writer in w["writers"]:
            if writer["transform"]:
                run_reads.setdefault(writer["transform"], []).extend(writer["read"])

    # ── Lane 0: sources ─────────────────────────────────────────────────────
    connectors = [c for c in list_connectors() if not c["warehouse"]]
    stored = {(c.get("storage") or {}).get("where") for c in connectors} - {None}
    for c in sorted(connectors, key=lambda c: c["name"]):
        name = c["name"]
        sid = f"source:{name}"
        storage = c.get("storage") or {}
        chip = (_DIALECT.get(c.get("dialect"), "SQL") if c.get("type") == "SQLConnector"
                else _TYPE.get(c.get("type"), (c.get("type") or "").replace("Connector", "")))
        where = storage.get("where")
        # A file is named by its path; anything else by its kind and the
        # variable that sets it. storage.where never resolves a credential;
        # a password in a literal URL is masked all the same.
        where = _CREDENTIAL.sub(r"://\1:***@", where) if where else where
        origin = where if storage.get("kind") == "file" and where else (
            f"{chip} · {where}" if where else chip)
        readers = [f"transform:{t['name']}" for t in c["read_by"]["transforms"]]
        read_tables = list(dict.fromkeys(tb for t in c["read_by"]["transforms"] for tb in t["tables"]))
        connector = registry.get_connector(name)
        listing = connection_tables(connector) if connector is not None else {"connected": False}
        connected = bool(listing.get("connected"))
        listed = {t["name"]: t for t in (listing.get("tables") or [])}
        snapshots = [r for t in readers for r in run_reads.get(t.split(":", 1)[1], [])
                     if r.get("connection") == name and r.get("snapshot")]
        if snapshots:
            moved = {"at": _mtime(os.path.join(root, snapshots[0]["snapshot"])), "how": "snapshot"}
        elif storage.get("kind") == "file" and where:
            moved = {"at": _mtime(os.path.join(root, where)), "how": "changed"}
        else:
            moved = {"at": None, "how": "changed"}
        trust = {"state": "warn", "text": "Read from snapshot"} if snapshots else dict(_NOT_A_SINK)
        tables = list(dict.fromkeys([*listed, *read_tables]))
        allowed = [t for t in tables if agent_may_read(connector, t)] if connector is not None else []
        agents = ({"state": "ok", "text": f"{len(allowed)} of {_plural(len(tables), 'table')}"}
                  if allowed else {"state": "none", "text": "No tables ticked"})
        sub = [_plural(len(tables), "table")] if tables else []
        if not connected:
            sub.append("not connected here")
        sub.append(f"read by {_names(readers)}" if readers else "read by no transform")
        nodes.append(_node(
            sid, "source", SOURCES, name=name, label=c.get("label") or name, chip=chip,
            sub=" · ".join(sub), open_=f"/data/sources/{_seg(name)}", origin=origin,
            readers=readers, writers=[], moved=moved, trust=trust, agents=agents,
            reach={"connected": connected, "variable": listing.get("variable")}))
        edges += [[sid, r] for r in readers]
        for table in tables:
            t_readers = [f"transform:{t['name']}" for t in c["read_by"]["transforms"]
                         if table in t["tables"]]
            info = listed.get(table) or {}
            may = connector is not None and agent_may_read(connector, table)
            facts = []
            if isinstance(info.get("rows"), int):
                facts.append(_plural(info["rows"], "row"))
            if info.get("columns"):
                facts.append(_plural(len(info["columns"]), "column"))
            facts.append(f"read by {_names(t_readers)}" if t_readers else "read by no transform")
            nodes.append(_node(
                f"source_table:{name}.{table}", "source_table", SOURCES, parent=sid,
                name=table, label=table, chip=chip, sub=" · ".join(facts),
                open_=f"/data/sources/{_seg(name)}/{_segs(table)}", origin=origin,
                readers=t_readers, writers=[], moved=moved, trust=trust,
                agents=({"state": "ok", "text": "Agents may read it"} if may
                        else {"state": "none", "text": "Not ticked for agents"}),
                rows=info.get("rows")))

    # Every data file under inputs/ (a CSV, Parquet, JSON, Excel: the kinds a
    # transform reads), but one a connection already stands for (a SQLite
    # file): that connection is its node. A seed script or a note beside the
    # data is not a source, so it is never a gap.
    for f in list_inputs()["files"]:
        path = f["path"]
        ext = PurePosixPath(path).suffix.lower().lstrip(".")
        if path in stored or ext not in _EXT:
            continue
        fid = f"file:{path}"
        readers = [f"transform:{t}" for t in f["read_by"]]
        rel = path.removeprefix("inputs/")
        nodes.append(_node(
            fid, "file", SOURCES, name=path, label=PurePosixPath(path).name,
            chip=_EXT.get(ext, ext.upper() or "File"),
            sub=f"read by {_names(readers)}" if readers else "no transform reads it",
            open_=(f"/data/sources/inputs/{_segs(rel)}" if f.get("table") else "/data/sources/inputs"),
            origin=path, readers=readers, writers=[],
            moved={"at": f.get("modified"), "how": "changed"}, trust=dict(_NOT_A_SINK),
            agents={"state": "none", "text": "Files are never read by agents"},
            reach={"connected": None, "variable": None},
            gap=None if readers else "no transform reads it"))
        edges += [[fid, r] for r in readers]

    # ── Lane 1: transforms ──────────────────────────────────────────────────
    groups_of: dict[str, list[str]] = {}          # transform → its group ids
    for w in whs:
        for writer in w["writers"]:
            if writer["transform"]:
                gid = f"group:{writer['transform']}"
                if gid not in groups_of.setdefault(writer["transform"], []):
                    groups_of[writer["transform"]].append(gid)
    for t in transforms:
        name = t["name"]
        tid = f"transform:{name}"
        in_flow = bool(t["pipelines"] or t["tables"])
        # Where it comes from: what its last run read (the certificate), else
        # what its file names; and the input files it names.
        reads: dict[str, list[dict]] = {}
        for r in run_reads.get(name, []):
            reads.setdefault(r.get("connection"), []).append(r)
        said = []
        for conn, rs in reads.items():
            snap = " (snapshot)" if any(r.get("snapshot") for r in rs) else ""
            said.append(f"{conn}.{rs[0]['table']}{snap}" if len(rs) == 1
                        else f"{conn} · {_plural(len(rs), 'table')}")
        said += [a.split(":", 1)[1] for a, z in edges if z == tid
                 and (a.startswith("file:") or (not reads and a.startswith("source:")))]
        written = [c for w in whs for tb in w["tables"]
                   if (tb.get("written_by") or {}).get("transform") == name
                   for c in [tb.get("contract")]]
        checks = sum(wr["checks"] for w in whs for wr in w["writers"] if wr["transform"] == name)
        nodes.append(_node(
            tid, "transform", TRANSFORMS, name=name, label=name,
            chip=_FORM.get(t["form"], t["form"]),
            sub=(f"writes {_plural(len(t['tables']), 'table')}" if t["tables"]
                 else "no pipeline runs it" if not in_flow else "has not written here yet"),
            open_=f"/data/transforms/{_seg(name)}", origin=" · ".join(said) or t["file"],
            readers=groups_of.get(name, []), writers=[],
            moved={"at": t["written_at"], "how": "written" if t["written_at"] else "never"},
            trust=_checks_trust(written, checks) if written else {"state": "none", "text": "No checks"},
            agents={"state": "none", "text": "May propose a change"},
            gap=None if in_flow else "no pipeline runs it"))

    # ── Lane 2: the warehouse, a group per writer ───────────────────────────
    many = len(whs) > 1
    groups: dict[str, dict] = {}
    for w in whs:
        writers = {wr["contract"]: wr for wr in w["writers"]}
        for tb in w["tables"]:
            record = (tb.get("written_by") or {}).get("contract")
            wr = writers.get(record) if record else None
            key = (wr["transform"] or wr["contract"]) if wr else _LOOSE
            g = groups.setdefault(key, {"transform": wr["transform"] if wr else None,
                                        "contract": record if wr else None,
                                        "warehouse": w, "writer": wr, "tables": []})
            g["tables"].append((w, tb))
    for key, g in sorted(groups.items(), key=lambda kv: (kv[0] == _LOOSE, kv[0])):
        gid = f"group:{key}"
        transform = g["transform"]
        writers = [f"transform:{transform}"] if transform in by_transform else []
        models = list(dict.fromkeys(m for _, tb in g["tables"] for m in tb["read_by"]))
        tables = [tb for _, tb in g["tables"]]
        facts = [tb["name"] for tb in tables if tb["name"].startswith("fact")][:2]
        rest = len(tables) - len(facts)
        sub = " · ".join(facts + ([f"{rest} more"] if rest and facts else [])) or " · ".join(
            tb["name"] for tb in tables[:3])
        wr = g["writer"] or {}
        w = g["warehouse"]
        nodes.append(_node(
            gid, "group", WAREHOUSE, name=key,
            label=f"written by {transform or g['contract']}" if wr else "written outside a transform",
            chip=_plural(len(tables), "table"), sub=sub,
            open_=(f"/data/warehouse?group={_seg(w['name'] + ':' + g['contract'])}" if g["contract"]
                   else "/data/warehouse"),
            origin=w.get("where") or w["name"], readers=[f"model:{m}" for m in models],
            writers=writers, moved={"at": wr.get("at"), "how": "written" if wr.get("at") else "never"},
            trust=_checks_trust([tb.get("contract") for tb in tables], wr.get("checks")),
            agents={"state": "ok", "text": "Through the model"}))
        edges += [[wid, gid] for wid in writers]
        edges += [[gid, f"model:{m}"] for m in models if registry.get_model(m) is not None]
        for wh, tb in g["tables"]:
            view = tb.get("kind") == "view"
            contract = tb.get("contract") or {}
            readers = [f"model:{m}" for m in tb["read_by"]]
            facts = []
            if isinstance(tb.get("rows"), int):
                facts.append(_plural(tb["rows"], "row"))
            facts.append(_plural(tb["columns"], "column"))
            facts.append(f"read by {_names(readers)}" if readers else "no model reads it")
            at = (tb.get("written_by") or {}).get("at")
            nodes.append(_node(
                f"table:{wh['name']}.{tb['name']}", "table", WAREHOUSE, parent=gid,
                name=tb["name"], label=tb["name"], chip="view" if view else "table",
                sub=" · ".join(facts),
                open_=f"/data/warehouse/{_seg(tb['name'])}" + (f"?warehouse={_seg(wh['name'])}" if many else ""),
                origin=(f"view over {', '.join(tb.get('bases') or [])}" if view and tb.get("bases")
                        else wh.get("where") or wh["name"]),
                readers=readers, writers=writers,
                moved={"at": at, "how": ("defined" if view else "written") if at else "never"},
                trust=_checks_trust([contract], contract.get("checks")),
                agents={"state": "ok", "text": "Through the model"},
                gap=None if readers else "no model reads it", rows=tb.get("rows")))

    # ── Lanes 3 and 4: models and the reports that read them ────────────────
    reports = list_reports()          # only those the caller may view
    read_by_model: dict[str, list[str]] = {}
    for r in reports:
        names = r.get("models") or ([r["name"].split("/", 1)[0]] if "/" in r["name"] else [])
        r["_models"] = [m for m in names if registry.get_model(m) is not None]
        for m in r["_models"]:
            read_by_model.setdefault(m, []).append(f"report:{r['name']}")
    group_of_table = {(wh["name"], tb["name"]): f"group:{key}"
                      for key, g in groups.items() for wh, tb in g["tables"]}
    contracts_of_table = {(wh["name"], tb["name"]): tb.get("contract")
                          for g in groups.values() for wh, tb in g["tables"]}
    for info in sorted(registry.list_models(), key=lambda m: m["name"]):
        name = info["name"]
        model = registry.get_model(name)
        mid = f"model:{name}"
        read = [(t["connector"], t["source"]) for t in (model.info().get("tables") or [])] if model else []
        writers = list(dict.fromkeys(group_of_table[k] for k in read if k in group_of_table))
        readers = read_by_model.get(name, [])
        wh_names = sorted({c for c, _ in read})
        n_tables, n_measures = len(info["tables"]), len(info["measures"])
        nodes.append(_node(
            mid, "model", MODELS, name=name, label=info.get("label") or name, chip="model",
            sub=f"{_plural(n_tables, 'table')} · {_plural(n_measures, 'measure')}",
            open_=f"/data/models/{_seg(name)}",
            origin=" · ".join(wh_names + [_plural(n_tables, "table")]),
            readers=readers, writers=writers,
            moved={"at": _mtime(model_path(name)), "how": "defined"},
            trust=_checks_trust([contracts_of_table.get(k) for k in read if k in contracts_of_table]),
            agents={"state": "ok", "text": "Full semantic layer"},
            gap=None if readers else "no report reads it"))
        edges += [[mid, r] for r in readers]

    models = _loaded_models()
    output = os.path.join(root, "output")
    for r in sorted(reports, key=lambda r: r["name"]):
        name = r["name"]
        html = os.path.join(output, *name.split("/")) + ".html"
        built = _mtime(html) if os.path.isfile(html) else None
        verdict = cached_verdict(html + ".manifest.json", models) if built else None
        state, text = _VERDICT.get((verdict or {}).get("verdict"), _NOT_CHECKED)
        made = {"app.jsx": "dashboard", "template.html": "page"}.get(r.get("made_from"), "report")
        nodes.append(_node(
            f"report:{name}", "report", REPORTS, name=name, label=r.get("display_name") or name,
            chip=made, sub=" · ".join(r["_models"]) or "reads no model",
            open_="/reports/" + _segs(name), origin=" · ".join(r["_models"]) or "no model",
            readers=[], writers=[f"model:{m}" for m in r["_models"]],
            moved={"at": built, "how": "built" if built else "never"},
            trust={"state": state, "text": text},
            agents={"state": "ok", "text": "Published"}))

    return {"summary": _summary(nodes), "nodes": nodes, "edges": edges}


def _summary(nodes: list[dict]) -> dict:
    """The bar's counts, from the nodes: each kind counts the nodes in the
    flow (wired on both sides), and ``gaps`` the rest."""
    def n(*kinds: str) -> int:
        return sum(1 for x in nodes if x["kind"] in kinds and not x["gap"])

    groups = [x for x in nodes if x["kind"] == "group"]
    return {
        "sources": n("source", "file"),
        "transforms": n("transform"),
        "tables": n("table"),
        "models": n("model"),
        "reports": n("report"),
        "gaps": sum(1 for x in nodes if x["gap"]),
        "stale": sum(1 for x in nodes if x["kind"] == "table"
                     and x["passport"]["trust"]["text"] == _CHECKS["stale"][1]),
        "checks": {
            "satisfied": sum(1 for g in groups if g["passport"]["trust"]["state"] == "ok"),
            "of": sum(1 for g in groups if g["passport"]["trust"]["text"] != _CHECKS["no_contract"][1]),
        },
        "agents": {
            "source_tables": sum(1 for x in nodes if x["kind"] == "source_table"
                                 and x["passport"]["agents"]["state"] == "ok"),
            "models": sum(1 for x in nodes if x["kind"] == "model"),
            "reports": sum(1 for x in nodes if x["kind"] == "report"),
        },
    }
