"""Where each column of a SQL transform's sink comes from, as DuckDB parses it.

A SQL transform (``transforms/<name>.sql``) is read by DuckDB's own parser
(``json_serialize_sql``), statement by statement, while it runs. For every
table and view the script leaves in the warehouse, each column records the
columns it is computed from: the ``-- source:`` tables (``crm.issuer_ratings.rating``),
the files read under the project (``inputs/holdings.csv.par``) and the
warehouse's other tables (``dim_rating.rating_id``, so a view's columns chain
through its bases). ``TEMP`` tables, common table expressions and macros are
followed through and do not appear as bases; the ``TEMP`` tables a column
passed through are named in ``via``.

**Nothing is inferred.** A column's ``from`` is the union of every column its
expression references (arguments, ``CASE`` branches, a window's
``PARTITION BY`` and ``ORDER BY``, every column a scalar subquery reads), as
the parse tree says. A ``WHERE``, a join condition or a ``GROUP BY`` decides
which rows, not what a value is computed from, and is not counted. ``SELECT
*`` expands through the run's own catalog at the moment the statement runs.
When the tree cannot be followed (a table macro, ``COLUMNS(…)``, a recursive
CTE, a table changed by a later ``INSERT``, a read of something that is
neither a source, a file nor a warehouse table) the column records ``from:
null`` and the reason, never a guess. An empty ``from`` is a proof too: the
column is computed from no column (a constant, ``row_number()``, ``range``).

A pandas or notebook transform records nothing: free-form code has no tree to
read, and the line stays at the sink (``MANIFESTO.md``, "The honest boundary").
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

#: Table functions that read a file: their first argument is the path.
_FILE_READERS = frozenset({
    "read_csv", "read_csv_auto", "read_parquet", "parquet_scan", "read_json",
    "read_json_auto", "read_ndjson", "read_ndjson_auto", "read_json_objects",
    "read_xlsx",
})
#: Table functions that make rows and read nothing: their columns come from no column.
_GENERATORS = frozenset({"range", "generate_series", "unnest"})
#: Statements that change a table's rows or columns after it was created.
_CHANGES = {"INSERT": ("INTO",), "UPDATE": (), "ALTER": ("TABLE", "VIEW"), "COPY": (),
            "MERGE": ("INTO",)}


def _token_shapes() -> dict:
    import duckdb

    return {duckdb.token_type.keyword: re.compile(r"\w+"),
            duckdb.token_type.identifier: re.compile(r'"(?:[^"]|"")*"|[^\s.(),;]+'),
            duckdb.token_type.operator: re.compile(r"(?:(?!--|/\*)[^\w\s\"'])+")}


class _Unresolved(Exception):
    """A whole statement's output cannot be followed; the reason says why."""


class _Col:
    """One column's provenance: base columns and the TEMP tables it passed
    through, or the reason it cannot be followed."""

    __slots__ = ("bases", "via", "reason")

    def __init__(self, bases=(), via=(), reason: Optional[str] = None) -> None:
        self.bases = frozenset(bases)
        self.via = frozenset(via)
        self.reason = reason

    @staticmethod
    def union(cols) -> "_Col":
        bases: set = set()
        via: set = set()
        for col in cols:
            if col.reason is not None:
                return col
            bases |= col.bases
            via |= col.via
        return _Col(bases, via)

    def through(self, temp: str) -> "_Col":
        return self if self.reason is not None else _Col(self.bases, self.via | {temp})

    def record(self) -> dict:
        if self.reason is not None:
            return {"from": None, "reason": self.reason}
        out: dict = {"from": sorted(self.bases)}
        if self.via:
            out["via"] = sorted(self.via)
        return out


_NONE = _Col()


class _Rel:
    """A relation in a FROM clause: its alias and its columns in order."""

    def __init__(self, alias: str, cols: list[tuple[str, _Col]]) -> None:
        self.alias = alias.lower()
        self.cols = cols

    def get(self, name: str) -> Optional[_Col]:
        for col, lin in self.cols:
            if col.lower() == name.lower():
                return lin
        return None


class _Scope:
    """The relations one SELECT can see, the join's merged ``USING`` columns,
    the select list's earlier aliases, and the enclosing query's scope (a
    correlated subquery reads it)."""

    def __init__(self, rels: list[_Rel], using: dict, outer: Optional["_Scope"],
                 ctes: dict) -> None:
        self.rels = rels
        self.using = using          # {name: _Col}
        self.outer = outer
        self.ctes = ctes
        self.aliases: dict = {}     # lateral select-list aliases
        self.params: set = set()     # lambda parameters in reach


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# DuckDB's serialized tree is not a stable format: 2.0 renamed parts of it.
# Every read of a node goes through these, which accept the 1.5 and the 2.0
# shape and, for anything else, raise _Unresolved naming the node and the part
# that is missing, so an unknown shape is a reason, never a KeyError.

def _what(node: Any) -> str:
    if isinstance(node, dict):
        kind = node.get("class") or node.get("type")
        if kind:
            return f"a {str(kind).lower().replace('_', ' ')} node"
    return f"a {type(node).__name__}"


def _part(node: Any, *keys: str) -> Any:
    """``node[k1][k2]…``, or _Unresolved naming the node and the missing key."""
    at = node
    for key in keys:
        if not isinstance(at, dict) or at.get(key) is None:
            import duckdb

            raise _Unresolved(f"{_what(node)} without {'.'.join(keys)} in DuckDB "
                              f"{duckdb.__version__}'s parse tree")
        at = at[key]
    return at


def _cte_query(value: dict) -> dict:
    """A CTE's query node: ``query_node`` in 2.0, ``query.node`` in 1.5."""
    if isinstance(value, dict) and isinstance(value.get("query_node"), dict):
        return value["query_node"]
    return _part(value, "query", "node")


def _args(fn: dict) -> list:
    """A function's arguments: ``arguments: [{name, expression}]`` in 2.0,
    ``children`` in 1.5."""
    if isinstance(fn.get("arguments"), list) and (fn["arguments"] or "children" not in fn):
        return [_part(a, "expression") if isinstance(a, dict) and "expression" in a else a
                for a in fn["arguments"]]
    return list(fn.get("children") or [])


def _string(expr: Any) -> Optional[str]:
    """A string literal's text: ``literal: {kind: STRING, text}`` in 2.0,
    ``value: {type: {id: VARCHAR}, value}`` in 1.5; None for anything else."""
    if not isinstance(expr, dict) or expr.get("class") != "CONSTANT":
        return None
    literal = expr.get("literal")
    if isinstance(literal, dict):
        return literal.get("text") if literal.get("kind") == "STRING" else None
    value = expr.get("value")
    if isinstance(value, dict) and isinstance(value.get("value"), str):
        return value["value"]
    return None


def _tree(con, sql: str) -> dict:
    tree = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    if tree.get("error"):
        raise _Unresolved(f"DuckDB could not serialize it ({tree.get('error_message')})")
    statements = tree.get("statements") or []
    if len(statements) != 1:
        raise _Unresolved("it is not one query")
    return statements[0]


class Tracer:
    """Follows one SQL transform's statements through one connection.

    Call :meth:`before` with each statement's text before it runs and
    :meth:`after` once it has; :meth:`result` gives the lineage of the tables
    and views still in the warehouse. A failure inside the tracer never stops
    the run: the tables it concerns record ``from: null`` and why."""

    def __init__(self, con, sources: list[str], root: Optional[str] = None) -> None:
        self.con = con
        self.sources = {s.lower(): s for s in sources}
        self.root = os.path.abspath(root) if root else None
        self.temps: dict[str, list[tuple[str, _Col]]] = {}   # TEMP tables and views
        self.sinks: dict[str, list[tuple[str, _Col]]] = {}   # created in the warehouse
        self.names: dict[str, str] = {}                      # lower → as created
        self._pending: Optional[tuple] = None
        self._target = ""
        self._macros: dict[str, Optional[str]] = {}
        self._n = 0

    # ── The statement loop ──────────────────────────────────────────────

    def before(self, sql: str) -> None:
        self._n += 1
        self._pending = None
        try:
            head = _head(sql)
        except Exception:  # noqa: BLE001 — the tokenizer refused it; the run will say why
            return
        if head is None:
            return
        kind, temp, name, body = head
        if kind == "CREATE":
            self._target = (name or "").split(".")[-1].lower()
            try:
                if body is None:
                    raise _Unresolved("it is created without a query and filled by "
                                      "statements the reader does not follow")
                cols: Any = self._query(_part(_tree(self.con, body), "node"), None, {})
            except _Unresolved as exc:
                cols = f"statement {self._n} cannot be followed: {exc}"
            except Exception as exc:  # noqa: BLE001 — never guess, never fail the run
                cols = (f"statement {self._n} has a shape the reader does not follow "
                        f"({type(exc).__name__}: {' '.join(str(exc).split())[:200]})")
            self._pending = (temp, name, cols)
        elif kind == "DROP":
            self._forget(name)
        elif kind in _CHANGES:
            reason = (f"statement {self._n} ({kind}) changes it after it was created, "
                      f"and the reader follows only the CREATE … AS that made it")
            key = (name or "").lower()
            targets = [key] if key else list(self.temps) + list(self.sinks)
            for target in targets:
                for store in (self.temps, self.sinks):
                    if target in store:
                        store[target] = [(c, _Col(reason=reason)) for c, _ in store[target]]

    def after(self) -> None:
        if self._pending is None:
            return
        temp, name, cols = self._pending
        self._pending = None
        bare = name.split(".")[-1]
        qualifier = name.rsplit(".", 1)[0].lower() if "." in name else ""
        if qualifier not in ("", "main", "temp", self._database().lower()):
            return      # made in another catalog: not the warehouse's
        try:
            names = [r[0] for r in self.con.execute(f"DESCRIBE {_ident(bare)}").fetchall()]
        except Exception:  # noqa: BLE001 — a qualified or unusual target: not followed
            return
        if isinstance(cols, str):
            lineage = [_Col(reason=cols)] * len(names)
        elif len(cols) != len(names):
            reason = (f"statement {self._n}: the query's columns and the table DuckDB "
                      f"created do not line up")
            lineage = [_Col(reason=reason)] * len(names)
        else:
            lineage = [c for _, c in cols]
        self._forget(bare)
        store = self.temps if temp else self.sinks
        store[bare.lower()] = list(zip(names, lineage))
        self.names[bare.lower()] = bare

    def result(self) -> dict:
        """``{table: {column: {"from": [...], "via": [...]} | {"from": None, "reason": …}}}``
        for each table and view the script created that the warehouse still holds."""
        present = {r[0].lower() for r in self.con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
            "AND schema_name = 'main' AND NOT temporary "
            "UNION SELECT view_name FROM duckdb_views() WHERE database_name = current_database() "
            "AND schema_name = 'main' AND NOT internal AND NOT temporary").fetchall()}
        return {self.names[key]: {col: lin.record() for col, lin in cols}
                for key, cols in sorted(self.sinks.items()) if key in present}

    def _forget(self, name: Optional[str]) -> None:
        key = (name or "").split(".")[-1].lower()
        self.temps.pop(key, None)
        self.sinks.pop(key, None)

    # ── Queries ──────────────────────────────────────────────────────────

    def _query(self, node: dict, outer: Optional[_Scope], ctes: dict) -> list[tuple[str, _Col]]:
        ctes = self._ctes(node, outer, ctes)
        kind = node.get("type")
        if kind == "SELECT_NODE":
            return self._select(node, outer, ctes)
        if kind == "SET_OPERATION_NODE":
            return self._setop(node, outer, ctes)
        if kind == "RECURSIVE_CTE_NODE":
            raise _Unresolved("a recursive CTE")
        raise _Unresolved(f"a {str(kind).lower().replace('_', ' ')}")

    def _ctes(self, node: dict, outer: Optional[_Scope], ctes: dict) -> dict:
        entries = (node.get("cte_map") or {}).get("map") or []
        if not entries:
            return ctes
        ctes = dict(ctes)
        for entry in entries:
            value = entry.get("value") or {}
            cols = self._query(_cte_query(value), outer, ctes)
            cols = _renamed(cols, value.get("aliases") or [])
            ctes[str(entry.get("key")).lower()] = cols
        return ctes

    def _setop(self, node: dict, outer, ctes) -> list[tuple[str, _Col]]:
        # 1.5 has left and right; 2.0 a list of children (left and right null).
        sides = [self._query(node[k], outer, ctes) for k in ("left", "right")] \
            if node.get("left") is not None else [self._query(c, outer, ctes)
                                                  for c in node.get("children") or []]
        if len(sides) < 2:
            raise _Unresolved(f"{_what(node)} with {len(sides)} side(s)")
        op = node.get("setop_type")
        if op in ("EXCEPT", "INTERSECT"):
            return sides[0]     # the right side only removes rows
        if op == "UNION_BY_NAME":
            out: dict = {}
            for side in sides:
                for name, col in side:
                    if name is None:
                        raise _Unresolved("UNION BY NAME over a column with no name")
                    key = name.lower()
                    out[key] = (out[key][0], _Col.union([out[key][1], col])) if key in out \
                        else (name, col)
            return list(out.values())
        if op != "UNION" or any(len(s) != len(sides[0]) for s in sides):
            raise _Unresolved(f"a set operation the reader does not follow ({op})")
        return [(sides[0][i][0], _Col.union([s[i][1] for s in sides]))
                for i in range(len(sides[0]))]

    def _select(self, node: dict, outer, ctes) -> list[tuple[str, _Col]]:
        rels, using = self._from(node.get("from_table") or {"type": "EMPTY"}, outer, ctes)
        scope = _Scope(rels, using, outer, ctes)
        out: list[tuple[str, _Col]] = []
        for expr in node.get("select_list") or []:
            if expr.get("class") == "STAR":
                out += self._star(expr, scope)
                continue
            col = self._expr(expr, scope)
            name = expr.get("alias") or None
            if name is None and expr.get("class") == "COLUMN_REF":
                name = _part(expr, "column_names")[-1]
            if name:
                scope.aliases.setdefault(name.lower(), col)
            out.append((name, col))
        return out

    def _star(self, expr: dict, scope: _Scope) -> list[tuple[str, _Col]]:
        if expr.get("columns") or expr.get("expr") is not None:
            raise _Unresolved("COLUMNS(…) selects columns by pattern")
        if expr.get("qualified_exclude_list") or expr.get("rename_list"):
            raise _Unresolved("a * with a qualified EXCLUDE or RENAME")
        relation = (expr.get("relation_name") or "").lower()
        rels = [r for r in scope.rels if not relation or r.alias == relation]
        if relation and not rels:
            raise _Unresolved(f"{expr.get('relation_name')}.* names no relation in reach")
        exclude = {str(e).lower() for e in expr.get("exclude_list") or []}
        replace = {str(e.get("key")).lower(): e.get("value") for e in expr.get("replace_list") or []}
        out: list[tuple[str, _Col]] = []
        seen_using: set = set()
        for rel in rels:
            for name, col in rel.cols:
                key = name.lower()
                if key in scope.using and not relation:
                    if key in seen_using:
                        continue        # a USING column appears once
                    seen_using.add(key)
                    col = scope.using[key]
                if key in exclude:
                    continue
                if key in replace:
                    col = self._expr(replace[key], scope)
                out.append((name, col))
        return out

    # ── FROM ─────────────────────────────────────────────────────────────

    def _from(self, ref: dict, outer, ctes) -> tuple[list[_Rel], dict]:
        kind = ref.get("type")
        if kind == "EMPTY":
            return [], {}
        if kind == "JOIN":
            left, lusing = self._from(ref["left"], outer, ctes)
            # The right side sees the left (a LATERAL join reads it).
            right, rusing = self._from(ref["right"], _Scope(left, lusing, outer, ctes), ctes)
            using = {**lusing, **rusing}
            names = [str(c) for c in ref.get("using_columns") or []]
            if ref.get("ref_type") == "NATURAL":
                lnames = {c.lower() for r in left for c, _ in r.cols}
                names = [c for r in right for c, _ in r.cols if c.lower() in lnames]
            join = ref.get("join_type")
            for name in names:
                lcol = _first(left, name)
                rcol = _first(right, name)
                if lcol is None or rcol is None:
                    raise _Unresolved(f"USING ({name}) names a column not on both sides")
                # An unqualified USING column is the left side's on an inner or
                # left join, the right side's on a right join, both on a full one.
                using[name.lower()] = {"INNER": lcol, "LEFT": lcol, "SEMI": lcol, "ANTI": lcol,
                                       "RIGHT": rcol}.get(join, _Col.union([lcol, rcol]))
            if join in ("SEMI", "ANTI"):
                right = []      # a semi or anti join keeps only the left's columns
            return left + right, using
        alias = ref.get("alias") or ""
        if kind == "BASE_TABLE":
            name = ref.get("table_name") or ""
            cols = self._table(ref, ctes)
            rel = _Rel(alias or name, cols)
        elif kind == "SUBQUERY":
            rel = _Rel(alias, self._query(_part(ref, "subquery", "node"), outer, ctes))
        elif kind == "TABLE_FUNCTION":
            rel = _Rel(alias or str(_part(ref, "function").get("function_name")),
                       self._function_table(ref, outer, ctes))
        elif kind == "EXPRESSION_LIST":
            scope = _Scope([], {}, outer, ctes)
            rows = ref.get("values") or []
            width = len(rows[0]) if rows else 0
            cols = [(f"col{i}", _Col.union(self._expr(row[i], scope) for row in rows))
                    for i in range(width)]
            rel = _Rel(alias, cols)
        else:
            raise _Unresolved(f"a {str(kind).lower().replace('_', ' ')} in FROM")
        rel.cols = _renamed(rel.cols, ref.get("column_name_alias") or [])
        return [rel], {}

    def _table(self, ref: dict, ctes: dict) -> list[tuple[str, _Col]]:
        catalog = ref.get("catalog_name") or ""
        schema = ref.get("schema_name") or ""
        name = ref.get("table_name") or ""
        key = name.lower()
        shown = ".".join(p for p in (catalog, schema, name) if p)
        if not catalog and not schema and key in ctes:
            return ctes[key]
        qualifier = (catalog or schema).lower()
        if qualifier in self.sources:
            # Two parts (crm.issuer_ratings) parse as schema.table; DuckDB
            # binds the first to the source's catalog.
            conn = self.sources[qualifier]
            cols = self._describe(f"SELECT * FROM {_ident(conn)}.main.{_ident(name)}")
            return [(c, _Col({f"{conn}.{name}.{c}"})) for c in cols]
        own = qualifier in ("", "main", self._database().lower())
        if own and key in self.temps and qualifier != "main":
            return [(c, col.through(self.names[key])) for c, col in self.temps[key]]
        if own and key == self._target:
            if key in self.sinks:
                # CREATE OR REPLACE x AS … FROM x: the earlier x of this run.
                return self.sinks[key]
            if self._in_warehouse(name):
                raise _Unresolved(f"it reads its own previous rows ({shown})")
        if own and key in self.sinks:
            # Made earlier in this run: a base of the warehouse.
            return [(c, _Col({f"{self.names[key]}.{c}"})) for c, _ in self.sinks[key]]
        if own and self._in_warehouse(name):
            cols = self._describe(f"SELECT * FROM main.{_ident(name)}")
            return [(c, _Col({f"{name}.{c}"})) for c in cols]
        if not catalog and not schema and not self._in_catalog(name):
            # A quoted path in FROM ('inputs/x.csv'): DuckDB's replacement scan reads the file.
            try:
                cols = self._describe(f"SELECT * FROM {_ident(name)}")
            except Exception:  # noqa: BLE001
                cols = None
            if cols is not None:
                path = self._path(name)
                return [(c, _Col({f"{path}.{c}"})) for c in cols]
        raise _Unresolved(f"it reads {shown}, which is not a -- source: table, a file "
                          f"or a table of the warehouse")

    def _function_table(self, ref: dict, outer, ctes) -> list[tuple[str, _Col]]:
        fn = _part(ref, "function")
        fname = str(fn.get("function_name") or "").lower()
        ordinal = ref.get("with_ordinality") == "WITH_ORDINALITY"
        bare = {**ref, "alias": "", "column_name_alias": [], "with_ordinality": "WITHOUT_ORDINALITY"}
        if fname in _FILE_READERS:
            args = _args(fn)
            literal = _string(args[0]) if args else None
            if literal is None:
                raise _Unresolved(f"{fname}(…) reads a path that is not one literal")
            path = self._path(literal)
            # Asked without the statement's aliases, so a base is the file's own column.
            cols = self._describe(_select_star(self.con, bare))
            out = [(c, _Col({f"{path}.{c}"})) for c in cols]
        elif fname in _GENERATORS:
            scope = _Scope([], {}, outer, ctes)
            made = _Col.union(self._expr(a, scope) for a in _args(fn))
            out = [(c, made) for c in self._describe(_select_star(self.con, bare))]
        else:
            raise _Unresolved(f"it reads the table function {fname}(…), which the reader "
                              f"does not follow")
        if ordinal:
            out.append(("ordinality", _NONE))     # WITH ORDINALITY numbers the rows
        return out

    # ── Expressions ─────────────────────────────────────────────────────

    def _expr(self, expr: Any, scope: _Scope) -> _Col:
        if isinstance(expr, list):
            return _Col.union(self._expr(e, scope) for e in expr)
        if not isinstance(expr, dict):
            return _NONE
        cls = expr.get("class")
        if cls == "COLUMN_REF":
            return self._column(_part(expr, "column_names"), scope)
        if cls == "STAR":
            raise _Unresolved("an expression over * or COLUMNS(…)")
        if cls == "SUBQUERY":
            return self._subquery(expr, scope)
        if cls == "LAMBDA":
            inner = _Scope([], {}, scope, scope.ctes)
            inner.params = {n.lower() for n in _lambda_params(expr.get("lhs"))}
            return self._expr(expr.get("expr"), inner)
        if cls == "POSITIONAL_REFERENCE":
            raise _Unresolved("a positional reference (#n)")
        if cls == "FUNCTION":
            reason = self._macro_reads(str(expr.get("function_name") or ""))
            if reason:
                return _Col(reason=reason)
        return _Col.union(self._expr(v, scope) for k, v in expr.items()
                          if isinstance(v, (dict, list)))

    def _subquery(self, expr: dict, scope: _Scope) -> _Col:
        """Everything a scalar, ``IN`` or ``EXISTS`` subquery reads: its value
        is decided by its WHERE as much as by its select list (a lookup)."""
        node = _part(expr, "subquery", "node")
        parts = [self._expr(expr.get("child"), scope)]
        parts += [c for _, c in self._query(node, scope, scope.ctes)]
        parts.append(self._clauses(node, scope))
        return _Col.union(parts)

    def _clauses(self, node: dict, outer: _Scope) -> _Col:
        if node.get("type") != "SELECT_NODE":
            return _NONE
        ctes = self._ctes(node, outer, outer.ctes)
        rels, using = self._from(node.get("from_table") or {"type": "EMPTY"}, outer, ctes)
        scope = _Scope(rels, using, outer, ctes)
        parts = [self._expr(node.get(k), scope)
                 for k in ("where_clause", "having", "qualify", "group_expressions")]
        parts.append(self._conditions(node.get("from_table") or {}, scope))
        return _Col.union(parts)

    def _conditions(self, ref: dict, scope: _Scope) -> _Col:
        if ref.get("type") != "JOIN":
            return _NONE
        return _Col.union([self._expr(ref.get("condition"), scope),
                           self._conditions(ref["left"], scope),
                           self._conditions(ref["right"], scope)])

    def _column(self, names: list[str], scope: Optional[_Scope]) -> _Col:
        shown = ".".join(names)
        while scope is not None:
            found = _bind([n.lower() for n in names], scope)
            if found is not None:
                return found
            scope = scope.outer
        return _Col(reason=f"the column {shown} is not bound to anything the reader follows")

    def _macro_reads(self, name: str) -> Optional[str]:
        """A scalar macro's body is an expression over its parameters, so its
        arguments are what it reads, unless the body holds a subquery (it
        reads a table) or calls such a macro."""
        key = name.lower()
        if key in self._macros:
            return self._macros[key]
        self._macros[key] = None
        row = self.con.execute(
            "SELECT macro_definition FROM duckdb_functions() "
            "WHERE function_type = 'macro' AND lower(function_name) = ? LIMIT 1", [key]).fetchone()
        if row is not None and row[0]:
            try:
                tree = _tree(self.con, f"SELECT {row[0]}")
                listed = _part(tree, "node", "select_list")
                reads = _reads_table(listed) or any(self._macro_reads(f) for f in _functions(listed))
            except _Unresolved:
                reads = True
            if reads:
                self._macros[key] = (f"it calls the macro {name}, whose body reads a table "
                                     f"the reader does not follow")
        return self._macros[key]

    # ── The catalog ─────────────────────────────────────────────────────

    def _describe(self, sql: str) -> list[str]:
        return [r[0] for r in self.con.execute(f"DESCRIBE {sql}").fetchall()]

    def _database(self) -> str:
        return self.con.execute("SELECT current_database()").fetchone()[0]

    def _in_warehouse(self, name: str) -> bool:
        return self.con.execute(
            "SELECT count(*) FROM (SELECT table_name AS n FROM duckdb_tables() "
            "WHERE database_name = current_database() AND schema_name = 'main' AND NOT temporary "
            "UNION ALL SELECT view_name FROM duckdb_views() WHERE database_name = current_database() "
            "AND schema_name = 'main' AND NOT internal AND NOT temporary) WHERE lower(n) = ?",
            [name.lower()]).fetchone()[0] > 0

    def _in_catalog(self, name: str) -> bool:
        return self.con.execute(
            "SELECT count(*) FROM (SELECT table_name AS n FROM duckdb_tables() "
            "UNION ALL SELECT view_name FROM duckdb_views()) WHERE lower(n) = ?",
            [name.lower()]).fetchone()[0] > 0

    def _path(self, path: str) -> str:
        """A file as the project names it: relative to the root when under it."""
        if self.root and os.path.isabs(path):
            rel = os.path.relpath(path, self.root)
            if not rel.startswith(".."):
                return rel.replace(os.sep, "/")
        return path


def column_lineage(statements: list[str], con, sources: tuple = (),
                   root: Optional[str] = None) -> dict:
    """Run *statements* on *con* in order, following each with DuckDB's
    parse of it, and return the lineage of the tables and views they leave
    in the connection's own catalog (:meth:`Tracer.result`). *sources* names
    the attached ``-- source:`` connections. :func:`tracebi.transforms.run_sql`
    drives a :class:`Tracer` itself, inside its own statement loop."""
    tracer = Tracer(con, list(sources), root)
    for sql in statements:
        tracer.before(sql)
        con.execute(sql)
        tracer.after()
    return tracer.result()


# ── Helpers ─────────────────────────────────────────────────────────────

_TOKEN: Optional[dict] = None


def _head(sql: str) -> Optional[tuple]:
    """``(kind, temp, name, body)`` from DuckDB's tokens: a CREATE of a table
    or view (``body`` the query after its top-level ``AS``, None without
    one), a DROP, or a statement that changes a table (``name`` its target,
    None when the tokens do not say). None for anything else."""
    import duckdb

    global _TOKEN
    if _TOKEN is None:
        _TOKEN = _token_shapes()
    tokens = duckdb.tokenize(sql)
    raw = sql.encode("utf-8")     # the tokens' offsets count bytes
    words: list[tuple[int, str, Any]] = []
    for i, (start, kind) in enumerate(tokens):
        end = tokens[i + 1][0] if i + 1 < len(tokens) else len(raw)
        if kind == duckdb.token_type.comment:
            continue
        # A token runs to the next one, so a comment after it rides along.
        text = raw[start:end].decode("utf-8", "replace")
        shape = _TOKEN.get(kind)
        if shape is not None:
            text = shape.match(text).group(0) if shape.match(text) else text.strip()
        words.append((start, text.strip(), kind))
    if not words:
        return None
    upper = [w[1].upper() for w in words]
    first = upper[0]
    if first == "CREATE":
        i = 1
        if upper[i:i + 2] == ["OR", "REPLACE"]:
            i += 2
        temp = upper[i] in ("TEMP", "TEMPORARY")
        i += temp
        if upper[i] not in ("TABLE", "VIEW"):
            return None
        i += 1
        if upper[i:i + 3] == ["IF", "NOT", "EXISTS"]:
            i += 3
        name, i = _name(words, i)
        depth = 0
        for j in range(i, len(words)):
            if words[j][2] == duckdb.token_type.operator:
                depth += words[j][1].count("(") - words[j][1].count(")")
            if depth == 0 and upper[j] == "AS" and words[j][2] == duckdb.token_type.keyword:
                return "CREATE", temp, name, raw[words[j][0] + 2:].decode("utf-8")
        return "CREATE", temp, name, None
    if first == "DROP" and len(upper) > 1 and upper[1] in ("TABLE", "VIEW"):
        i = 2 + (upper[2:4] == ["IF", "EXISTS"]) * 2
        return "DROP", False, _name(words, i)[0], None
    if first in _CHANGES:
        i = 1
        if first == "INSERT" and upper[1:3] == ["OR", "REPLACE"]:
            i = 3
        expect = _CHANGES[first]
        if expect:
            if i >= len(upper) or upper[i] not in expect:
                return first, False, None, None
            i += 1
        if first == "COPY" and i < len(upper) and upper[i] == "(":
            return None     # COPY (query) TO …: writes a file, changes no table
        name, j = _name(words, i)
        if first == "COPY" and (j >= len(upper) or upper[j] != "FROM"):
            return None     # COPY table TO …: reads it, changes nothing
        return first, False, name, None
    return None


def _name(words: list, i: int) -> tuple[Optional[str], int]:
    """A possibly qualified name starting at token *i*, unquoted."""
    parts: list[str] = []
    while i < len(words):
        text = words[i][1]
        if text.startswith('"') and text.endswith('"') and len(text) > 1:
            text = text[1:-1].replace('""', '"')
        elif not (text[:1].isalpha() or text[:1] == "_"):
            break
        parts.append(text)
        i += 1
        if i < len(words) and words[i][1] == ".":
            i += 1
            continue
        break
    return (".".join(parts) or None), i


def _renamed(cols: list, aliases: list) -> list:
    return [(aliases[i] if i < len(aliases) else name, col) for i, (name, col) in enumerate(cols)]


def _first(rels: list[_Rel], name: str) -> Optional[_Col]:
    for rel in rels:
        col = rel.get(name)
        if col is not None:
            return col
    return None


def _bind(names: list[str], scope: _Scope) -> Optional[_Col]:
    """A column reference in one scope, as DuckDB binds it: ``col``,
    ``rel.col``, ``schema.rel.col`` or ``catalog.schema.rel.col``, else a
    struct field of a column (``col.field``). None when this scope has no
    such column (the enclosing one is tried next)."""
    col = names[-1]
    if len(names) == 1:
        if col in scope.params:
            return _NONE
        if col in scope.using:
            return scope.using[col]
        found = [r.get(col) for r in scope.rels if r.get(col) is not None]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            return _Col(reason=f"the column {col} is ambiguous")
        return scope.aliases.get(col)
    for k in range(len(names) - 1, 0, -1):
        rel = names[k - 1]
        for r in scope.rels:
            if r.alias == rel and r.get(names[k]) is not None:
                return r.get(names[k])      # names past k are struct fields
    if names[0] in scope.params:
        return _NONE
    if len(names) >= 2:
        # col.field: a struct field of a column in reach.
        found = _bind([names[0]], scope)
        if found is not None:
            return found
    return None


def _lambda_params(lhs: Any) -> list[str]:
    if isinstance(lhs, dict):
        if lhs.get("class") == "COLUMN_REF":
            return [_part(lhs, "column_names")[-1]]
        return [p for c in _args(lhs) for p in _lambda_params(c)]
    return []


def _reads_table(node: Any) -> bool:
    if isinstance(node, list):
        return any(_reads_table(n) for n in node)
    if not isinstance(node, dict):
        return False
    if node.get("class") == "SUBQUERY" or node.get("type") in ("BASE_TABLE", "TABLE_FUNCTION"):
        return True
    return any(_reads_table(v) for v in node.values())


def _functions(node: Any) -> list[str]:
    if isinstance(node, list):
        return [f for n in node for f in _functions(n)]
    if not isinstance(node, dict):
        return []
    here = [str(node["function_name"])] if node.get("class") == "FUNCTION" else []
    return here + [f for v in node.values() for f in _functions(v)]


def _select_star(con, ref: dict) -> str:
    """``SELECT * FROM <ref>`` as SQL, written back by DuckDB from the tree,
    so its columns are asked of the catalog exactly as the statement names it.
    The SELECT around *ref* is DuckDB's own serialization of one, so it has
    the shape this version of DuckDB reads back."""
    doc = json.loads(con.execute("SELECT json_serialize_sql('SELECT * FROM __tracebi_ref')").fetchone()[0])
    _part(doc["statements"][0], "node")["from_table"] = ref
    return con.execute("SELECT json_deserialize_sql(?::JSON)", [json.dumps(doc)]).fetchone()[0]
