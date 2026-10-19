"""
SilverLayer / ManipulationLayer — clean, type-cast, deduplicate, and lightly
transform raw data.

The new canonical name is ``ManipulationLayer`` — it matches TraceBi's
framing: optional light touches (joins, casts, filters, renames) before
serving. ``SilverLayer`` remains a fully supported alias for back-compat.

Each step appends a lineage node with the layer's ``operation`` tag
("manipulation" or "silver").

The declarative steps compile to SQL and run in DuckDB (``tracebi/etl/_sql.py``):
inside the warehouse when the source and the sink are the same DuckDB
database, over the source's ``load()`` frame as Arrow otherwise. Each node's
metadata carries ``engine: duckdb`` and the step's SELECT. ``transform(func)``
is the escape hatch: it runs a pandas callable, and its node says
``escape_hatch: python``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

from tracebi.connectors.base import BaseConnector
from tracebi.etl import _sql
from tracebi.model.dataset import DataSet, LineageNode

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


class SilverLayer:
    """
    Declarative cleaning pipeline for landing/bronze data.

    Every method is fluent and returns ``self``.
    Call ``apply(dataset)`` for standalone use or ``execute()`` for pipelines.

    Standalone usage::

        silver = (
            SilverLayer()
            .cast({"qty": "int64"})
            .drop_nulls(subset=["order_id"])
            .deduplicate(subset=["order_id"])
        )
        clean_ds = silver.apply(raw_ds, name="orders_silver")
    """

    operation: str = "silver"
    layer_label: str = "silver"

    def __init__(
        self,
        source: Optional[BaseConnector] = None,
        source_table: Optional[str] = None,
        sink: Optional[BaseConnector] = None,
        sink_table: Optional[str] = None,
    ) -> None:
        self._steps: list[dict[str, Any]] = []
        self._source = source
        self._source_table = source_table
        self._sink = sink
        self._sink_table = sink_table

    # ── Step declarations ──────────────────────────────────────

    def cast(self, type_map: dict[str, str]) -> "SilverLayer":
        """Cast columns to pandas dtype names (``int64``, ``float64``, ``str``,
        ``datetime64[ns]`` …); ``_sql.CAST_TYPES`` lists them, and any other
        name is refused when the layer runs."""
        self._steps.append({"op": "cast", "type_map": type_map})
        return self

    def drop_nulls(self, subset: Optional[list[str]] = None) -> "SilverLayer":
        self._steps.append({"op": "drop_nulls", "subset": subset})
        return self

    def deduplicate(self, subset: Optional[list[str]] = None) -> "SilverLayer":
        """Keep the first row of each *subset* key (all columns by default).

        "First" is the source's order: a DuckDB table's insertion order
        (``rowid``), a frame's row order, the order its ``load()`` returned for
        any other connector. A DuckDB view has no stored order, so its rows are
        numbered as the scan returns them, which is the order ``SELECT *``
        would have given pandas.
        """
        self._steps.append({"op": "deduplicate", "subset": subset})
        return self

    def rename(self, columns: dict[str, str]) -> "SilverLayer":
        self._steps.append({"op": "rename", "columns": columns})
        return self

    def filter(self, where: str, description: str = "") -> "SilverLayer":
        """Keep the rows where the SQL condition *where* holds (DuckDB syntax,
        e.g. ``"status <> 'cancelled'"``)."""
        self._steps.append({"op": "filter", "where": where, "description": description})
        return self

    def transform(
        self,
        func: Callable[["pd.DataFrame"], "pd.DataFrame"],
        description: str = "",
    ) -> "SilverLayer":
        """The escape hatch: run *func* on the rows so far as a pandas frame.

        Everything else in the layer is SQL; this step is Python, and its
        lineage node (and the runner's record of the run) says so.
        """
        self._steps.append({"op": "transform", "func": func, "description": description})
        return self

    # ── Execution ──────────────────────────────────────────────

    def apply(self, dataset: DataSet, name: Optional[str] = None) -> DataSet:
        output_name = name or f"{dataset.name}_{self.layer_label}"
        duckdb = _sql.require_duckdb()
        con = duckdb.connect()
        try:
            con.register("__tb_input", _sql.arrow_with_rows(dataset.to_pandas()))
            last, nodes, _ = _sql.run_steps(
                con, _sql.quote("__tb_input"), self._steps, self.operation, self.layer_label)
            df = _sql.to_frame(con, last)
        finally:
            con.close()
        return DataSet(df=df, name=output_name, lineage=list(dataset.lineage) + nodes)

    def execute(self):
        """Load the source, run the steps, write the sink.

        Returns a ``DataSet``, or — when the source and the sink are one DuckDB
        database and the work never left it — a ``_sql.SinkTable`` with the
        same ``len()``, ``lineage`` and ``to_pandas()``.
        """
        if self._source is None or self._source_table is None:
            raise RuntimeError(
                f"{type(self).__name__}.execute() requires 'source' and 'source_table'."
            )
        if self._sink is None or self._sink_table is None:
            raise RuntimeError(
                f"{type(self).__name__}.execute() requires 'sink' and 'sink_table'."
            )
        if (_sql.same_database(self._source, self._sink)
                and self._source_table in self._source.list_tables()):
            return self._execute_in_warehouse()
        raw_df = self._source.load(self._source_table)
        load_node = LineageNode(
            operation="load",
            description=f"Pipeline load: '{self._source_table}' from '{self._source.name}'",
            connector={
                "connector_name": self._source.name,
                "connector_type": type(self._source).__name__,
            },
            source=self._source_table,
            metadata={"rows_loaded": len(raw_df)},
        )
        input_ds = DataSet(df=raw_df, name=self._source_table, lineage=[load_node])
        ds = self.apply(input_ds, name=self._sink_table)
        self._sink.write(ds.to_pandas(), self._sink_table)
        return ds

    def _execute_in_warehouse(self) -> "_sql.SinkTable":
        """Source → steps → sink as SQL in the one database; no frame is loaded
        unless a ``transform`` step asks for one."""
        if self._source is not self._sink:
            # Another handle on the same file: DuckDB refuses to open one file
            # read-only and read-write in the same process at once.
            self._source.disconnect()
        q = _sql.quote
        source, sink = self._source_table, self._sink_table
        with self._sink.write_connection() as con:
            order = "rowid" if _sql.table_kind(con, source) == "table" else "row_number() OVER ()"
            base_sql = f"SELECT *, {order} AS {_sql.ROW} FROM {q(source)}"
            con.execute(f"CREATE TEMP VIEW {q('__tb_source')} AS {base_sql}")
            created = [("view", "__tb_source")]
            try:
                rows_in = _sql.count(con, q("__tb_source"))
                last, nodes, made = _sql.run_steps(
                    con, q("__tb_source"), self._steps, self.operation, self.layer_label)
                created += made
                con.execute(
                    f"CREATE OR REPLACE TABLE {q(sink)} AS "
                    f"SELECT * EXCLUDE ({_sql.ROW}) FROM {last} ORDER BY {_sql.ROW}"
                )
                rows_out = _sql.count(con, q(sink))
                columns = [c for c, _ in _sql.describe(con, q(sink))]
            finally:
                _sql.drop(con, created)
        load_node = LineageNode(
            operation="load",
            description=f"Pipeline load: '{source}' from '{self._source.name}'",
            connector={
                "connector_name": self._source.name,
                "connector_type": type(self._source).__name__,
            },
            source=source,
            metadata={"rows_loaded": rows_in, "engine": "duckdb", "sql": base_sql},
        )
        return _sql.SinkTable(self._sink, sink, rows_out, columns, [load_node] + nodes)

    def __repr__(self) -> str:
        step_names = [s["op"] for s in self._steps]
        return f"<{type(self).__name__} steps={step_names} sink_table={self._sink_table!r}>"


class ManipulationLayer(SilverLayer):
    """
    Manipulation layer — optional light touches before serving.

    TraceBi-positioned name for the cleaning step (joins, casts, filters,
    renames). Identical behaviour to ``SilverLayer`` but stamps lineage
    with ``operation="manipulation"``.
    """

    operation: str = "manipulation"
    layer_label: str = "manipulation"
