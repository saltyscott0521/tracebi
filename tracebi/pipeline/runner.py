"""
PipelineRunner — schedule and execute medallion layers with full lineage tracking.

Each layer is registered independently with its own cron schedule.
The runner records every execution in ``tracebi_runs`` and persists DataModel
config (relationships, facts, dimensions) to system tables in the DB.

Usage::

    from tracebi.pipeline.runner import PipelineRunner

    runner = PipelineRunner(db_url="sqlite:///data/tracebi.db")

    runner.register(bronze, name="orders_bronze", schedule="0 * * * *")
    runner.register(silver, name="orders_silver", schedule="30 * * * *",
                    depends_on="orders_bronze")
    runner.register(gold,   name="revenue_by_region", schedule="0 6 * * *",
                    depends_on="orders_silver")

    runner.run("orders_bronze")                      # on-demand, bronze only
    runner.run("revenue_by_region", refresh=True)    # full chain: bronze→silver→gold
    runner.lineage("revenue_by_region")              # print run history
    runner.start()                                   # start APScheduler (blocking)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from tracebi.etl.bronze import BronzeLayer
from tracebi.etl.silver import SilverLayer
from tracebi.etl.gold import GoldLayer


@dataclass
class _LayerReg:
    name: str
    layer: Any
    schedule: Optional[str]
    depends_on: Optional[str]
    layer_type: str


class PipelineRunner:
    """
    Orchestrator for medallion pipeline layers.

    Stores run history and schema config in a SQLite (or any SQLAlchemy)
    database so every execution is traceable across sessions.
    """

    # System table DDL
    _DDL = [
        """CREATE TABLE IF NOT EXISTS tracebi_layers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    UNIQUE NOT NULL,
            layer_type  TEXT    NOT NULL,
            schedule    TEXT,
            source_table TEXT,
            sink_table  TEXT,
            depends_on  TEXT,
            created_at  TEXT    NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS tracebi_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            layer_name      TEXT NOT NULL,
            layer_type      TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            completed_at    TEXT,
            status          TEXT NOT NULL,
            rows_in         INTEGER,
            rows_out        INTEGER,
            upstream_run_id INTEGER,
            error_message   TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS tracebi_schemas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_name TEXT NOT NULL,
            model_name  TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS tracebi_dimensions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_id   INTEGER NOT NULL,
            dim_name    TEXT NOT NULL,
            table_name  TEXT NOT NULL,
            key_col     TEXT NOT NULL,
            attributes  TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS tracebi_facts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_id   INTEGER NOT NULL,
            fact_name   TEXT NOT NULL,
            table_name  TEXT NOT NULL,
            measures    TEXT NOT NULL,
            foreign_keys TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS tracebi_relationships (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name  TEXT NOT NULL,
            rel_name    TEXT NOT NULL,
            left_table  TEXT NOT NULL,
            right_table TEXT NOT NULL,
            left_key    TEXT NOT NULL,
            right_key   TEXT NOT NULL,
            how         TEXT NOT NULL DEFAULT 'left'
        )""",
    ]

    def __init__(self, db_url: str = "sqlite:///data/tracebi.db") -> None:
        self._db_url = db_url
        self._layers: dict[str, _LayerReg] = {}
        self._engine = None
        self._scheduler = None
        self._init_db()

    # ── DB setup ───────────────────────────────────────────────

    def _engine_(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(self._db_url)
        return self._engine

    def _init_db(self) -> None:
        from sqlalchemy import text
        engine = self._engine_()
        with engine.begin() as conn:
            for ddl in self._DDL:
                conn.execute(text(ddl))

    # ── Registration ───────────────────────────────────────────

    def register(
        self,
        layer: Any,
        name: str,
        schedule: Optional[str] = None,
        depends_on: Optional[str] = None,
    ) -> "PipelineRunner":
        """
        Register a layer with the runner.

        Args:
            layer:      A BronzeLayer, SilverLayer, or GoldLayer instance
                        configured with ``sink`` / ``sink_table``.
            name:       Unique logical name for this layer.
            schedule:   Cron expression (5 fields): ``"0 6 * * *"``.
                        ``None`` means on-demand only.
            depends_on: Name of the upstream layer that feeds this one.
                        Used by ``run(refresh=True)`` to walk the full chain.
        """
        if depends_on and depends_on not in self._layers:
            raise ValueError(
                f"depends_on='{depends_on}' is not registered. "
                f"Register upstream layers first."
            )

        # LandingLayer/ManipulationLayer/FinalLayer are subclasses, so the
        # isinstance check covers both naming conventions. Use the layer's
        # own label so the new names propagate to run history.
        layer_type = getattr(layer, "layer_label", None) or (
            "bronze" if isinstance(layer, BronzeLayer) else
            "silver" if isinstance(layer, SilverLayer) else
            "gold"   if isinstance(layer, GoldLayer)   else
            type(layer).__name__.lower()
        )
        self._layers[name] = _LayerReg(
            name=name,
            layer=layer,
            schedule=schedule,
            depends_on=depends_on,
            layer_type=layer_type,
        )

        source_table = getattr(layer, "_source_table", None) or getattr(layer, "_source", None)
        sink_table   = getattr(layer, "_sink_table", None)

        from sqlalchemy import text
        with self._engine_().begin() as conn:
            conn.execute(text("""
                INSERT OR REPLACE INTO tracebi_layers
                  (name, layer_type, schedule, source_table, sink_table, depends_on, created_at)
                VALUES
                  (:name, :layer_type, :schedule, :source_table, :sink_table, :depends_on, :ts)
            """), {
                "name":         name,
                "layer_type":   layer_type,
                "schedule":     schedule,
                "source_table": source_table,
                "sink_table":   sink_table,
                "depends_on":   depends_on,
                "ts":           datetime.now(timezone.utc).isoformat(),
            })
        return self

    def register_model(self, model) -> "PipelineRunner":
        """
        Persist a DataModel's relationships, facts, and dimensions to the DB.

        Call this once after ``register()`` calls so the model definition
        is stored alongside run history.
        """
        from sqlalchemy import text
        with self._engine_().begin() as conn:
            for rel in model._relationships.values():
                conn.execute(text("""
                    INSERT INTO tracebi_relationships
                      (model_name, rel_name, left_table, right_table,
                       left_key, right_key, how)
                    VALUES (:mn, :rn, :lt, :rt, :lk, :rk, :how)
                """), {
                    "mn":  model.name,
                    "rn":  rel.name,
                    "lt":  rel.left_table,
                    "rt":  rel.right_table,
                    "lk":  rel.left_key,
                    "rk":  rel.right_key,
                    "how": rel.how,
                })

            if not model._facts and not model._dimensions:
                return self

            conn.execute(text("""
                INSERT INTO tracebi_schemas (schema_name, model_name, created_at)
                VALUES (:sn, :mn, :ts)
            """), {
                "sn": model.name,
                "mn": model.name,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            schema_id = conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]

            for dim in model._dimensions.values():
                conn.execute(text("""
                    INSERT INTO tracebi_dimensions
                      (schema_id, dim_name, table_name, key_col, attributes)
                    VALUES (:sid, :dn, :tn, :kc, :attrs)
                """), {
                    "sid":   schema_id,
                    "dn":    dim.name,
                    "tn":    dim.table_name,
                    "kc":    dim.key_col,
                    "attrs": ",".join(dim.attributes),
                })

            for fact in model._facts.values():
                fk_str = ",".join(f"{k}:{v}" for k, v in fact.foreign_keys.items())
                conn.execute(text("""
                    INSERT INTO tracebi_facts
                      (schema_id, fact_name, table_name, measures, foreign_keys)
                    VALUES (:sid, :fn, :tn, :m, :fk)
                """), {
                    "sid": schema_id,
                    "fn":  fact.name,
                    "tn":  fact.table_name,
                    "m":   ",".join(fact.measures),
                    "fk":  fk_str,
                })
        return self

    # ── Execution ──────────────────────────────────────────────

    def run(self, name: str, refresh: bool = False) -> None:
        """
        Execute a registered layer on demand.

        Args:
            name:    Registered layer name.
            refresh: When ``True``, walk the ``depends_on`` chain and run
                     every upstream layer in order before running *name*.
                     When ``False`` (default), run *name* only.
        """
        if name not in self._layers:
            raise ValueError(
                f"Layer '{name}' is not registered. "
                f"Available: {list(self._layers.keys())}"
            )
        chain = self._resolve_chain(name) if refresh else [name]
        if refresh:
            print(f"\n[PipelineRunner] Refresh: {' → '.join(chain)}")
        for layer_name in chain:
            self._execute(layer_name)

    def start(self, blocking: bool = True) -> None:
        """
        Start APScheduler with all registered cron schedules.

        Args:
            blocking: When ``True`` (default), runs in the foreground and
                      blocks until Ctrl+C. When ``False``, runs in a
                      background thread — useful for tests and notebooks.
        """
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            raise ImportError(
                "apscheduler is required for scheduling.\n"
                "Install with: pip install 'apscheduler>=3.10'"
            )

        Scheduler = BlockingScheduler if blocking else BackgroundScheduler
        self._scheduler = Scheduler()

        scheduled = 0
        for name, reg in self._layers.items():
            if not reg.schedule:
                continue
            parts = reg.schedule.split()
            if len(parts) != 5:
                raise ValueError(
                    f"Invalid cron expression for '{name}': '{reg.schedule}'. "
                    "Expected 5 fields: minute hour day month day_of_week"
                )
            minute, hour, day, month, dow = parts
            self._scheduler.add_job(
                func=lambda n=name: self._execute(n),
                trigger="cron",
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=dow,
                id=name,
                name=name,
                misfire_grace_time=300,
            )
            print(f"  Scheduled: {name}  [{reg.schedule}]")
            scheduled += 1

        if scheduled == 0:
            print("[PipelineRunner] No layers have a schedule — nothing to start.")
            return

        print(f"\n[PipelineRunner] Started with {scheduled} scheduled layer(s).")
        if blocking:
            print("  Press Ctrl+C to stop.\n")
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self._scheduler.shutdown()
            print("\n[PipelineRunner] Stopped.")

    def stop(self) -> None:
        """Stop the scheduler if running."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()

    # ── Lineage / inspection ───────────────────────────────────

    def lineage(self, name: str, limit: int = 10) -> None:
        """
        Print run history for a layer and its full upstream chain.

        Args:
            name:  Registered layer name.
            limit: Max runs to show per layer (most recent first).
        """
        chain = self._resolve_chain(name)
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  Pipeline Lineage — '{name}'")
        print(f"  Chain: {' → '.join(chain)}")
        print(sep)

        for layer_name in chain:
            df = pd.read_sql(
                "SELECT * FROM tracebi_runs "
                f"WHERE layer_name = '{layer_name}' "
                f"ORDER BY id DESC LIMIT {limit}",
                con=self._engine_(),
            )
            reg = self._layers.get(layer_name)
            schedule = reg.schedule if reg else "—"
            print(f"\n  [{layer_name}]  schedule={schedule}  runs={len(df)}")
            if df.empty:
                print("    No runs recorded.")
            else:
                for _, row in df.iterrows():
                    icon = "✓" if row["status"] == "success" else "✗"
                    ts = str(row["started_at"])[:19]
                    print(
                        f"    {icon} run_id={row['id']:>4}  "
                        f"{ts}  "
                        f"rows {row['rows_in']} → {row['rows_out']}  "
                        f"[{row['status']}]"
                        + (f"  upstream_run={row['upstream_run_id']}"
                           if row["upstream_run_id"] else "")
                    )
        print(f"{sep}\n")

    def status(self) -> None:
        """Print a summary of all registered layers and their last run."""
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  PipelineRunner — {len(self._layers)} layer(s)")
        print(sep)
        for name, reg in self._layers.items():
            df = pd.read_sql(
                "SELECT status, completed_at, rows_out FROM tracebi_runs "
                f"WHERE layer_name = '{name}' "
                "ORDER BY id DESC LIMIT 1",
                con=self._engine_(),
            )
            if df.empty:
                last = "never run"
            else:
                row = df.iloc[0]
                ts = str(row["completed_at"] or "")[:19]
                last = f"{row['status']}  {ts}  rows_out={row['rows_out']}"
            schedule = reg.schedule or "on-demand"
            depends  = f" ← {reg.depends_on}" if reg.depends_on else ""
            print(f"  {name:30s}  [{reg.layer_type}]  {schedule}{depends}")
            print(f"    last run: {last}")
        print(f"{sep}\n")

    # ── Internal helpers ───────────────────────────────────────

    def _resolve_chain(self, name: str) -> list[str]:
        """Walk depends_on links and return execution order (upstream first)."""
        chain: list[str] = []
        current: Optional[str] = name
        seen: set[str] = set()
        while current is not None:
            if current in seen:
                break
            seen.add(current)
            chain.append(current)
            reg = self._layers.get(current)
            current = reg.depends_on if reg else None
        return list(reversed(chain))

    def _execute(self, name: str) -> None:
        reg = self._layers[name]
        started_at = datetime.now(timezone.utc).isoformat()
        upstream_run_id = self._latest_run_id(reg.depends_on) if reg.depends_on else None
        run_id = self._write_run_start(name, reg.layer_type, started_at, upstream_run_id)

        rows_in = rows_out = 0
        status = "failed"
        error_msg: Optional[str] = None

        print(f"  [{name}] Running ({reg.layer_type})...")
        try:
            ds = reg.layer.execute()
            rows_out = len(ds)
            # Pull rows_in from the load/bronze metadata if present
            for node in ds.lineage:
                val = node.metadata.get("rows_ingested") or node.metadata.get("rows_loaded")
                if val is not None:
                    rows_in = val
                    break
            if rows_in == 0:
                rows_in = rows_out
            status = "success"
            print(f"  [{name}] ✓  {rows_in} in → {rows_out} out")
        except Exception as exc:
            error_msg = str(exc)
            print(f"  [{name}] ✗  {error_msg}")
            raise
        finally:
            completed_at = datetime.now(timezone.utc).isoformat()
            self._write_run_end(run_id, completed_at, status, rows_in, rows_out, error_msg)

    def _latest_run_id(self, layer_name: Optional[str]) -> Optional[int]:
        if not layer_name:
            return None
        from sqlalchemy import text
        with self._engine_().connect() as conn:
            row = conn.execute(text(
                "SELECT id FROM tracebi_runs "
                "WHERE layer_name = :n AND status = 'success' "
                "ORDER BY id DESC LIMIT 1"
            ), {"n": layer_name}).fetchone()
        return row[0] if row else None

    def _write_run_start(
        self, name: str, layer_type: str, started_at: str, upstream_run_id: Optional[int]
    ) -> int:
        from sqlalchemy import text
        with self._engine_().begin() as conn:
            conn.execute(text("""
                INSERT INTO tracebi_runs
                  (layer_name, layer_type, started_at, status, upstream_run_id)
                VALUES (:n, :lt, :ts, 'running', :uid)
            """), {"n": name, "lt": layer_type, "ts": started_at, "uid": upstream_run_id})
            return conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]

    def _write_run_end(
        self,
        run_id: int,
        completed_at: str,
        status: str,
        rows_in: int,
        rows_out: int,
        error_msg: Optional[str],
    ) -> None:
        from sqlalchemy import text
        with self._engine_().begin() as conn:
            conn.execute(text("""
                UPDATE tracebi_runs
                SET completed_at = :ca, status = :s,
                    rows_in = :ri, rows_out = :ro, error_message = :em
                WHERE id = :id
            """), {
                "ca": completed_at, "s": status,
                "ri": rows_in, "ro": rows_out,
                "em": error_msg, "id": run_id,
            })

    def __repr__(self) -> str:
        return f"<PipelineRunner db={self._db_url!r} layers={list(self._layers.keys())}>"
