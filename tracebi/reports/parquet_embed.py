"""Parquet embed transport for the artifact data layer.

The artifact embeds a figure's data as **Parquet** — compact (≈50× smaller than
JSON on real data), and the format the client-side worker engine (parquet-wasm +
Arquero) decodes in the browser. See ``docs/large-detail-artifacts.md``.

The receipt is **unchanged** by this. The fingerprint is still the frame's
content triple — ``{columns, dtypes, csv}`` via
:func:`tracebi.model.dataset.frame_fingerprint` — which survives the Parquet
round-trip *exactly* (locked by ``tests/test_parquet_embed.py``): a frame written
to Parquet and read back has the identical content fingerprint. So Parquet is
**transport, not the hashed thing** — no ``fingerprint_algo`` change is needed,
and every receipt issued under the CSV embed stays valid. ``verify`` simply gains
a decode step: read the embedded Parquet, then recompute and compare the same
triple it always did.

DuckDB does the read/write: it is already a required connector dependency, is
present wherever the warehouse lives (the warehouse *is* DuckDB), and round-trips
the dtypes a query result carries without loss — unlike a pandas/pyarrow path,
which is neither declared nor available on every supported pandas.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


def _duckdb():
    try:
        import duckdb

        return duckdb
    except ImportError as exc:  # pragma: no cover - guarded per invariant 4
        raise ImportError(
            "Parquet embedding requires DuckDB. Install with: "
            "pip install 'tracebi[duckdb]'"
        ) from exc


def to_parquet_bytes(df: "pd.DataFrame") -> bytes:
    """Serialize *df* to Parquet (ZSTD) bytes for embedding.

    Parquet is transport only: the receipt is the frame's content fingerprint,
    which :func:`from_parquet_bytes` recovers exactly. The Parquet bytes
    themselves are never hashed (Parquet is not byte-reproducible across writers,
    and does not need to be).
    """
    duckdb = _duckdb()
    con = duckdb.connect()
    fd, path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    try:
        con.register("_tb_embed_src", df)
        # A zero-row result loses object-column typing through DuckDB's inference
        # (an empty object column reads back as int32), which would change the
        # fingerprint's dtypes and read as ALTERED. With no rows there is nothing
        # to corrupt, so pin object columns to VARCHAR to preserve the schema;
        # numeric/bool/datetime empty columns already round-trip unchanged.
        if len(df) == 0 and len(df.columns) > 0:
            projection = ", ".join(
                f'CAST("{c}" AS VARCHAR) AS "{c}"'
                if str(df[c].dtype) == "object"
                else f'"{c}"'
                for c in df.columns
            )
            source = f"SELECT {projection} FROM _tb_embed_src"
        else:
            source = "SELECT * FROM _tb_embed_src"
        # COPY's target must be a literal; mkstemp paths carry no quote chars.
        con.execute(
            f"COPY ({source}) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        con.close()
        try:
            os.unlink(path)
        except OSError:  # pragma: no cover
            pass


def from_parquet_bytes(data: bytes) -> "pd.DataFrame":
    """Decode embedded Parquet *data* back to a DataFrame — verify's decode step.

    The recovered frame has the same content fingerprint as the original, so
    verify recomputes ``{columns, dtypes, csv}`` from it and matches the stored
    ``embedded_sha256`` without any special-casing.
    """
    duckdb = _duckdb()
    con = duckdb.connect()
    fd, path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        return con.execute(f"SELECT * FROM read_parquet('{path}')").df()
    finally:
        con.close()
        try:
            os.unlink(path)
        except OSError:  # pragma: no cover
            pass
